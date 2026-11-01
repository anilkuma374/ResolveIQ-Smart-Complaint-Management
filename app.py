from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from config import DB_PATH
from database.db import initialize
from services.workflow import create_complaint, add_message, change_status, TRANSITIONS
from services.operations import (authenticate, create_customer, update_customer, evaluate_slas,
    run_data_quality, assign_least_loaded, create_user, record_first_response, now_iso)

st.set_page_config(page_title="ResolveIQ | Complaint Operations", page_icon="◈", layout="wide", initial_sidebar_state="expanded")

# ---------- visual system ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root{--ink:#17243a;--muted:#64748b;--line:#e5eaf2;--blue:#315efb;--mint:#dff8ef;--paper:#f6f8fc}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;color:var(--ink)}
.stApp{background:linear-gradient(180deg,#f8faff 0%,#f5f7fb 100%)}
.block-container{padding-top:1.4rem;padding-bottom:3rem;max-width:1500px}
[data-testid="stSidebar"]{background:#111d32;border-right:1px solid #23314a}
[data-testid="stSidebar"] *{color:#e8eefb!important}
[data-testid="stSidebar"] [data-testid="stRadio"] label{padding:8px 10px;border-radius:9px}
[data-testid="stSidebar"] [aria-checked="true"]{background:#263a5d;border-radius:9px}
.hero{background:linear-gradient(115deg,#172b4d 0%,#254d83 58%,#3978bd 100%);padding:27px 30px;border-radius:18px;color:white;margin:2px 0 22px;box-shadow:0 14px 35px rgba(29,57,98,.16)}
.hero h1{font-family:Manrope,sans-serif;color:white;font-size:29px;font-weight:800;margin:0 0 5px}.hero p{color:#d7e6fb;margin:0;font-size:14px}
.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:1.7px;font-weight:700;color:#a9c8f5;margin-bottom:9px}
.section-head{font-family:Manrope,sans-serif;font-size:20px;font-weight:800;color:#182944;margin:18px 0 12px}
.kpi{background:white;border:1px solid #e6ebf3;border-radius:15px;padding:17px 18px;box-shadow:0 4px 14px rgba(26,47,79,.035);min-height:110px}
.kpi .label{font-size:12px;color:#728097;font-weight:700;text-transform:uppercase;letter-spacing:.8px}.kpi .value{font-family:Manrope,sans-serif;font-size:29px;font-weight:800;color:#1d3150;margin-top:8px}.kpi .hint{font-size:11px;color:#8b98aa;margin-top:1px}
.panel{background:white;border:1px solid #e6ebf3;border-radius:15px;padding:18px 20px;box-shadow:0 4px 14px rgba(26,47,79,.025)}
div[data-testid="stMetric"]{background:white;border:1px solid #e6ebf3;padding:13px 16px;border-radius:13px;box-shadow:0 4px 14px rgba(26,47,79,.025)}
.stButton>button,.stFormSubmitButton>button{border-radius:9px;font-weight:700;border:0;padding:.55rem 1rem;min-height:42px}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:#315efb}
.stTextInput input,.stTextArea textarea,.stSelectbox div[data-baseweb="select"]>div,.stNumberInput input{border-radius:9px}
[data-testid="stDataFrame"]{border:1px solid #e8edf4;border-radius:11px;overflow:hidden}
hr{border-color:#e8edf4}
.small-muted{color:#7c8ba1;font-size:12px}
.status-pill{display:inline-block;border-radius:20px;padding:4px 9px;background:#edf2ff;color:#315efb;font-size:11px;font-weight:700}
.login-wrap{max-width:470px;margin:8vh auto;background:white;border:1px solid #e5eaf2;border-radius:20px;padding:30px;box-shadow:0 18px 50px rgba(25,45,75,.10)}
footer{visibility:hidden}
</style>
""", unsafe_allow_html=True)

if not DB_PATH.exists():
    st.error("Database not found. Extract the complete project folder and run the data generator.")
    st.code("python scripts/generate_data.py --seed 20261022 --scale 1.0")
    st.stop()
conn = initialize()

def read(sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)

def hero(kicker, title, subtitle):
    st.markdown(f'<div class="hero"><div class="eyebrow">{kicker}</div><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)

def kpi(label, value, hint=""):
    st.markdown(f'<div class="kpi"><div class="label">{label}</div><div class="value">{value}</div><div class="hint">{hint}</div></div>', unsafe_allow_html=True)

def can(user, *roles): return user["role"] in roles

# ---------- authentication ----------
if "user" not in st.session_state:
    st.session_state.user = None
if st.session_state.user is None:
    st.markdown('<div class="login-wrap"><div class="eyebrow" style="color:#315efb">CUSTOMER OPERATIONS PLATFORM</div><h1 style="font-family:Manrope;color:#172b4d;margin-bottom:4px">ResolveIQ</h1><p style="color:#718096;margin-top:0">Smart complaint intelligence & service operations</p>', unsafe_allow_html=True)
    with st.form("login"):
        username = st.text_input("Username", placeholder="Enter your username")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        go = st.form_submit_button("Sign in", type="primary", use_container_width=True)
    if go:
        user = authenticate(conn, username, password)
        if user: st.session_state.user = user; st.rerun()
        else: st.error("Invalid username or password, or account is inactive.")
    st.markdown('<p class="small-muted">Demo accounts: admin / Admin@123 · agent / Agent@123 · analyst / Analyst@123 · requester / Request@123</p></div>', unsafe_allow_html=True)
    st.stop()
user = st.session_state.user

# ---------- sidebar ----------
with st.sidebar:
    st.markdown("<div style='font-family:Manrope;font-size:23px;font-weight:800;color:white'>◈ ResolveIQ</div><div style='font-size:11px;color:#9fb2d0;margin:2px 0 18px'>SERVICE OPERATIONS SUITE</div>", unsafe_allow_html=True)
    st.markdown(f"**{user['display_name']}**  \n<span style='font-size:11px;color:#9fb2d0'>{user['role']}</span>", unsafe_allow_html=True)
    st.divider()
    if user["role"] == "Administrator":
        pages = ["Overview", "Complaint Workbench", "Register Complaint", "Customer Directory", "Products & Orders", "SLA & Escalations", "Notifications", "Data Quality", "Reports & Analytics", "Administration", "Data Dictionary"]
    elif user["role"] == "Agent":
        pages = ["Overview", "Complaint Workbench", "Register Complaint", "SLA & Escalations", "Notifications"]
    elif user["role"] == "Analyst":
        pages = ["Overview", "Complaint Workbench", "SLA & Escalations", "Notifications", "Data Quality", "Reports & Analytics", "Data Dictionary"]
    else:
        pages = ["Register Complaint", "My Complaints", "Notifications"]
    page = st.radio("WORKSPACE", pages, label_visibility="collapsed")
    st.divider()
    heartbeat = conn.execute("SELECT last_seen_at FROM AutomationHeartbeat WHERE worker_name='ResolveIQ Automation'").fetchone()
    if heartbeat:
        st.caption(f"Automation worker last active: {heartbeat['last_seen_at']}")
    else:
        st.caption("Automation worker: not started")
    st.caption("ResolveIQ · Academic prototype")
    if st.button("Sign out", use_container_width=True): st.session_state.user = None; st.rerun()

# Agent scoping for role-based access
agent_filter = ""
agent_params = []
if user["role"] == "Agent" and user.get("agent_id"):
    agent_filter = " AND EXISTS(SELECT 1 FROM Assignment ax WHERE ax.complaint_id=c.complaint_id AND ax.agent_id=? AND ax.is_current=1)"
    agent_params = [user["agent_id"]]

# ---------- overview ----------
if page == "Overview":
    hero("LIVE OPERATIONS OVERVIEW", "Good service starts with visibility.", "A single command centre for complaint volumes, customer experience, service levels and team performance.")
    evaluate_slas(conn, user["username"])
    c = read("SELECT * FROM Complaint c WHERE 1=1" + agent_filter, agent_params)
    sla = read("SELECT s.* FROM SLAClock s JOIN Complaint c USING(complaint_id) WHERE 1=1" + agent_filter, agent_params)
    total = len(c); open_n = int((~c.current_status.isin(["Resolved", "Closed"])).sum()) if total else 0
    breached = int(sla.clock_status.isin(["Breached", "Escalated"]).sum()) if len(sla) else 0
    resolved = int(c.current_status.isin(["Resolved", "Closed"]).sum()) if total else 0
    avg_resolution = read("SELECT AVG((julianday(s.resolved_at)-julianday(c.created_at))*24) hrs FROM SLAClock s JOIN Complaint c USING(complaint_id) WHERE s.resolved_at IS NOT NULL").iloc[0,0]
    a,b,d,e = st.columns(4)
    with a: kpi("Total complaints", f"{total:,}", "All registered cases")
    with b: kpi("Active workload", f"{open_n:,}", "Not yet resolved or closed")
    with d: kpi("SLA at risk / breached", f"{breached:,}", "Requires operational attention")
    with e: kpi("Resolved cases", f"{resolved:,}", f"Avg. resolution {avg_resolution:.1f} hrs" if pd.notna(avg_resolution) else "No completed cases yet")
    st.markdown('<div class="section-head">Service health</div>', unsafe_allow_html=True)
    left,right = st.columns([1.2,1])
    with left:
        daily = read("SELECT substr(created_at,1,10) day,COUNT(*) complaints FROM Complaint GROUP BY day ORDER BY day DESC LIMIT 30").sort_values("day")
        fig = px.area(daily,x="day",y="complaints",markers=True,title="Complaint intake · recent 30 active dates")
        fig.update_layout(height=330,margin=dict(l=10,r=10,t=55,b=10),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="white",font_color="#53647c")
        st.plotly_chart(fig,use_container_width=True)
    with right:
        pr = c.groupby("priority_level").size().reset_index(name="cases") if total else pd.DataFrame(columns=["priority_level","cases"])
        fig = px.pie(pr,names="priority_level",values="cases",hole=.65,title="Priority mix",color="priority_level",color_discrete_map={"Critical":"#dc4c64","High":"#f59e0b","Medium":"#4779dc","Low":"#36a98a"})
        fig.update_layout(height=330,margin=dict(l=10,r=10,t=55,b=10),paper_bgcolor="rgba(0,0,0,0)",legend_title_text="")
        st.plotly_chart(fig,use_container_width=True)
    x,y = st.columns(2)
    with x:
        st.markdown('<div class="section-head">Priority queue</div>',unsafe_allow_html=True)
        st.dataframe(read("SELECT complaint_id,priority_level,current_status,created_at FROM Complaint c WHERE current_status NOT IN ('Resolved','Closed')"+agent_filter+" ORDER BY CASE priority_level WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END,created_at LIMIT 10",agent_params),use_container_width=True,hide_index=True)
    with y:
        st.markdown('<div class="section-head">Team workload</div>',unsafe_allow_html=True)
        workload = read("SELECT t.team_name,COUNT(DISTINCT CASE WHEN c.current_status NOT IN ('Resolved','Closed') THEN c.complaint_id END) active_cases FROM Team t LEFT JOIN Assignment a USING(team_id) LEFT JOIN Complaint c USING(complaint_id) WHERE a.is_current=1 OR a.is_current IS NULL GROUP BY t.team_id ORDER BY active_cases DESC")
        st.dataframe(workload,use_container_width=True,hide_index=True)

# ---------- complaint workbench ----------
elif page == "Complaint Workbench":
    hero("CASE MANAGEMENT", "Complaint workbench", "Search, filter, inspect and progress customer cases from one operational queue.")
    p1,p2,p3,p4 = st.columns([1,1,1,1.5])
    with p1: pri = st.selectbox("Priority",["All","Critical","High","Medium","Low"])
    with p2: status = st.selectbox("Status",["All"]+["New","Triaged","Assigned","In Progress","Waiting for Customer","Resolved","Closed","Reopened","Escalated"])
    with p3: category = st.selectbox("Category",["All"]+read("SELECT category_name FROM Category ORDER BY category_name").category_name.tolist())
    with p4: search = st.text_input("Search cases",placeholder="ID, customer or keywords")
    sql = """SELECT c.complaint_id,cu.full_name customer,c.priority_level,c.severity,k.category_name,c.current_status,c.channel,c.created_at,
        a.agent_name assigned_agent,s.resolution_due_at FROM Complaint c LEFT JOIN Customer cu USING(customer_id)
        LEFT JOIN Category k USING(category_id) LEFT JOIN SLAClock s USING(complaint_id)
        LEFT JOIN Assignment x ON x.complaint_id=c.complaint_id AND x.is_current=1 LEFT JOIN Agent a USING(agent_id) WHERE 1=1"""
    params=[]
    if pri!="All": sql+=" AND c.priority_level=?";params.append(pri)
    if status!="All": sql+=" AND c.current_status=?";params.append(status)
    if category!="All": sql+=" AND k.category_name=?";params.append(category)
    if search: sql+=" AND (c.complaint_id LIKE ? OR cu.full_name LIKE ? OR c.description LIKE ?)";params += [f"%{search}%"]*3
    sql += agent_filter; params += agent_params
    sql += " ORDER BY CASE c.priority_level WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END,c.created_at DESC"
    cases=read(sql,params)
    st.caption(f"Showing {len(cases):,} matching complaints")
    st.dataframe(cases,use_container_width=True,hide_index=True,height=430)
    st.download_button("↓ Export filtered queue (CSV)",cases.to_csv(index=False),"complaint_queue.csv","text/csv")
    st.markdown('<div class="section-head">Case details & actions</div>',unsafe_allow_html=True)
    ids=cases.complaint_id.tolist()
    if ids:
        selected=st.selectbox("Open complaint",ids)
        details=read("SELECT c.*,cu.full_name,cu.email,cu.phone,k.category_name FROM Complaint c LEFT JOIN Customer cu USING(customer_id) LEFT JOIN Category k USING(category_id) WHERE complaint_id=?",(selected,)).iloc[0]
        top1,top2,top3,top4=st.columns(4)
        top1.metric("Priority",details.priority_level);top2.metric("Status",details.current_status);top3.metric("Category",details.category_name);top4.metric("Sentiment",f"{details.sentiment_score:.2f}")
        st.markdown(f"**{details.full_name}** · {details.email} · {details.phone}")
        st.write(details.description)
        sla=read("SELECT * FROM SLAClock WHERE complaint_id=?",(selected,))
        ass=read("SELECT a.agent_name,t.team_name,x.assigned_at,x.reason FROM Assignment x JOIN Agent a USING(agent_id) JOIN Team t USING(team_id) WHERE x.complaint_id=? AND x.is_current=1",(selected,))
        q1,q2=st.columns(2)
        with q1: st.markdown("**SLA clock**");st.dataframe(sla,use_container_width=True,hide_index=True)
        with q2: st.markdown("**Current assignment**");st.dataframe(ass,use_container_width=True,hide_index=True)
        if can(user,"Administrator"):
            with st.expander("Reassign case",expanded=False):
                teams=read("SELECT team_id,team_name FROM Team ORDER BY team_name")
                with st.form("reassign_case"):
                    team_label=st.selectbox("Destination team",teams.team_name.tolist())
                    if st.form_submit_button("Assign to least-loaded agent"):
                        team_id=teams.loc[teams.team_name==team_label,"team_id"].iloc[0]
                        agent_id=assign_least_loaded(conn,selected,team_id,user["username"])
                        if agent_id: st.success(f"Assigned to agent {agent_id}.");st.rerun()
                        else: st.error("No active agents are available in this team.")
        if can(user,"Administrator","Agent"):
            act1,act2=st.columns(2)
            with act1:
                allowed=sorted(TRANSITIONS.get(details.current_status,set()))
                with st.form("case_status"):
                    newstatus=st.selectbox("Move case to",allowed if allowed else [details.current_status],disabled=not allowed)
                    note=st.text_input("Audit note",value="Updated from ResolveIQ workbench")
                    if st.form_submit_button("Save status",type="primary",disabled=not allowed):
                        try: change_status(conn,selected,newstatus,user["username"],note);st.success("Status updated and audit trail recorded.");st.rerun()
                        except Exception as ex: st.error(str(ex))
            with act2:
                with st.form("case_message"):
                    msg=st.text_area("Add communication / internal note")
                    visible=st.checkbox("Visible to customer",True)
                    if st.form_submit_button("Add message"):
                        try: mid=add_message(conn,selected,"Agent" if user["role"]=="Agent" else "System",msg,visible=visible,sender_id=user["username"]);st.success(f"Message saved: {mid}");st.rerun()
                        except Exception as ex: st.error(str(ex))
        h1,h2=st.columns(2)
        with h1: st.markdown("**Status history**");st.dataframe(read("SELECT changed_at,from_status,to_status,changed_by,note FROM StatusEvent WHERE complaint_id=? ORDER BY changed_at DESC",(selected,)),use_container_width=True,hide_index=True)
        with h2: st.markdown("**Conversation history**");st.dataframe(read("SELECT created_at,sender_type,message_text,is_customer_visible FROM ComplaintMessage WHERE complaint_id=? ORDER BY created_at DESC",(selected,)),use_container_width=True,hide_index=True)
    else: st.info("No complaints match these filters.")

# ---------- register complaint ----------
elif page == "Register Complaint":
    hero("CUSTOMER INTAKE", "Register a complaint", "Capture the issue once. ResolveIQ classifies it, calculates priority and SLA, and routes it to the least-loaded eligible agent.")
    if can(user,"Administrator","Agent","Requester"):
        if user["role"] == "Requester":
            requester_row = conn.execute("SELECT customer_id FROM AppUser WHERE username=?", (user["username"],)).fetchone()
            customers = read("SELECT customer_id,full_name,email FROM Customer WHERE customer_id=? ORDER BY full_name", (requester_row["customer_id"],)) if requester_row and requester_row["customer_id"] else pd.DataFrame(columns=["customer_id","full_name","email"])
        else:
            customers=read("SELECT customer_id,full_name,email FROM Customer ORDER BY full_name")
        if customers.empty: st.warning("Create a customer record first.")
        else:
            with st.form("new_complaint",clear_on_submit=True):
                c1,c2=st.columns(2)
                customer_label=c1.selectbox("Customer",customers.apply(lambda r:f"{r.full_name} · {r.email}",axis=1).tolist())
                customer_id=customers.iloc[customers.apply(lambda r:f"{r.full_name} · {r.email}",axis=1).tolist().index(customer_label)].customer_id
                orders=read('SELECT order_id,customer_id,product_id,order_total FROM "Order" WHERE customer_id=? ORDER BY order_date DESC',(customer_id,))
                order_options=["No linked order"]+orders.order_id.tolist()
                order=c2.selectbox("Related order",order_options)
                channel=c1.selectbox("Contact channel",["Support Portal","Web","Email","Phone","Mobile App","Social Media"])
                sentiment=c2.slider("Customer sentiment",-1.0,1.0,-0.35,0.05,help="-1 = very negative; +1 = positive")
                description=st.text_area("Describe the issue",height=150,placeholder="Explain what happened, when it happened, and what outcome the customer expects...")
                submitted=st.form_submit_button("Create complaint & auto-route",type="primary",use_container_width=True)
            if submitted:
                try:
                    cid=create_complaint(conn,customer_id,None if order=="No linked order" else order,None,channel,description,sentiment,user["username"])
                    st.success(f"Complaint {cid} created. Classification, priority, SLA and workload-based assignment have been applied. The background worker will send the confirmation and assignment notifications within 30 seconds.")
                    st.balloons()
                except Exception as ex: st.error(f"Could not create complaint: {ex}")
    else: st.warning("Your role does not have permission to register complaints.")

# ---------- requester self-service portal ----------
elif page == "My Complaints":
    hero("CUSTOMER SELF-SERVICE", "My complaints", "Track your cases, read support updates and reply directly to your assigned team.")
    customer_id = user.get("customer_id")
    if not customer_id:
        st.warning("This requester account is not linked to a customer record. Ask an administrator to link it in the AppUser table.")
    else:
        mine = read("SELECT complaint_id,current_status,priority_level,created_at,updated_at FROM Complaint WHERE customer_id=? ORDER BY created_at DESC", (customer_id,))
        if mine.empty:
            st.info("You have not registered any complaints yet.")
        else:
            st.dataframe(mine,use_container_width=True,hide_index=True)
            selected = st.selectbox("Open one of your complaints",mine.complaint_id.tolist())
            st.markdown("**Conversation history**")
            conversation = read("SELECT created_at,sender_type,message_text FROM ComplaintMessage WHERE complaint_id=? AND is_customer_visible=1 ORDER BY created_at",(selected,))
            for _, message in conversation.iterrows():
                with st.chat_message("user" if message.sender_type=="Customer" else ("assistant" if message.sender_type=="System" else "human")):
                    st.caption(f"{message.sender_type} · {message.created_at}")
                    st.write(message.message_text)
            with st.form("customer_reply",clear_on_submit=True):
                reply = st.text_area("Send a reply to support",placeholder="Add details or answer the agent's question...")
                if st.form_submit_button("Send reply",type="primary"):
                    try:
                        add_message(conn,selected,"Customer",reply,channel="Support Portal",visible=True,sender_id=user["username"])
                        st.success("Your reply was saved. The automation worker will acknowledge it and notify the assigned agent within 30 seconds.")
                        st.rerun()
                    except Exception as ex: st.error(str(ex))

# ---------- notifications centre ----------
elif page == "Notifications":
    hero("COMMUNICATION CENTRE", "Notifications", "Review registration confirmations, assignments, SLA alerts, escalations and resolution updates.")
    if user["role"] == "Requester":
        notif = read("SELECT n.created_at,n.complaint_id,n.channel,n.subject,n.body,n.delivery_status FROM Notification n WHERE n.recipient_type='Customer' AND n.recipient_id=? ORDER BY n.created_at DESC LIMIT 300",(user.get("customer_id") or "",))
    elif user["role"] == "Agent":
        notif = read("SELECT n.created_at,n.complaint_id,n.channel,n.subject,n.body,n.delivery_status FROM Notification n WHERE (n.recipient_type='Agent' AND n.recipient_id=?) OR (n.recipient_type='User' AND n.recipient_id=?) ORDER BY n.created_at DESC LIMIT 300",(user.get("agent_id") or "",user["username"]))
    else:
        notif = read("SELECT n.created_at,n.complaint_id,n.recipient_type,n.recipient_id,n.channel,n.subject,n.body,n.delivery_status FROM Notification n ORDER BY n.created_at DESC LIMIT 500")
    st.caption(f"{len(notif)} notification records")
    if notif.empty: st.info("No notifications yet. Start the automation worker to process new events.")
    else:
        st.dataframe(notif,use_container_width=True,hide_index=True,height=520)
        st.download_button("Export notifications",notif.to_csv(index=False),"resolveiq_notifications.csv","text/csv")

# ---------- customers ----------
elif page == "Customer Directory":
    hero("CUSTOMER RECORDS", "Customer directory", "Maintain accurate customer profiles and review complaint history in one place.")
    customers=read("SELECT customer_id,full_name,email,phone,city,vulnerable_customer,created_at FROM Customer ORDER BY full_name")
    st.caption(f"{len(customers):,} customer records")
    st.dataframe(customers,use_container_width=True,hide_index=True,height=350)
    if can(user,"Administrator"):
        add,edit=st.tabs(["＋ Add customer","Edit customer"])
        with add:
            with st.form("add_customer"):
                n1,n2=st.columns(2);name=n1.text_input("Full name");email=n2.text_input("Email");phone=n1.text_input("Phone");city=n2.text_input("City");vuln=st.checkbox("Flag as vulnerable customer (restricted operational context)")
                if st.form_submit_button("Create customer",type="primary"):
                    try: cid=create_customer(conn,name,email,phone,city,vuln,user["username"]);st.success(f"Customer {cid} created.");st.rerun()
                    except Exception as ex: st.error(str(ex))
        with edit:
            if not customers.empty:
                cid=st.selectbox("Customer to edit",customers.customer_id.tolist())
                row=customers[customers.customer_id==cid].iloc[0]
                with st.form("edit_customer"):
                    name=st.text_input("Full name",row.full_name);email=st.text_input("Email",row.email);phone=st.text_input("Phone",row.phone);city=st.text_input("City",row.city);vuln=st.checkbox("Vulnerable customer",bool(row.vulnerable_customer))
                    if st.form_submit_button("Save customer changes",type="primary"):
                        try: update_customer(conn,cid,name,email,phone,city,vuln,user["username"]);st.success("Customer updated.");st.rerun()
                        except Exception as ex: st.error(str(ex))
    if not customers.empty:
        chosen=st.selectbox("View customer complaint history",customers.customer_id.tolist(),key="customer_history")
        st.dataframe(read("SELECT complaint_id,priority_level,current_status,created_at FROM Complaint WHERE customer_id=? ORDER BY created_at DESC",(chosen,)),use_container_width=True,hide_index=True)

# ---------- products & orders ----------
elif page == "Products & Orders":
    hero("COMMERCE DATA", "Products & orders", "Maintain the product catalogue and register customer orders used by complaint investigations.")
    products=read("SELECT product_id,product_name,product_type,unit_price,safety_sensitive,active FROM Product ORDER BY product_name")
    orders=read("""SELECT o.order_id,cu.full_name customer,p.product_name,o.order_date,o.quantity,o.order_total,o.order_status
        FROM "Order" o JOIN Customer cu USING(customer_id) JOIN Product p USING(product_id) ORDER BY o.order_date DESC LIMIT 1000""")
    tab1,tab2=st.tabs(["Product catalogue","Order register"])
    with tab1:
        st.dataframe(products,use_container_width=True,hide_index=True)
        if can(user,"Administrator"):
            with st.form("new_product"):
                st.markdown("**Add product**")
                p1,p2=st.columns(2);pname=p1.text_input("Product name");ptype=p2.text_input("Product type / category")
                price=p1.number_input("Unit price",min_value=0.0,step=100.0);safety=p2.checkbox("Safety-sensitive product")
                if st.form_submit_button("Add product",type="primary"):
                    try:
                        pid="PRD-"+str(conn.execute("SELECT COUNT(*) FROM Product").fetchone()[0]+1).zfill(4)
                        conn.execute("INSERT INTO Product(product_id,product_name,product_type,unit_price,safety_sensitive,active) VALUES(?,?,?,?,?,1)",(pid,pname.strip(),ptype.strip(),price,int(safety)))
                        conn.execute("INSERT INTO AuditLog(actor,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",(user["username"],"CREATE","Product",pid,pname.strip(),now_iso()))
                        conn.commit();st.success(f"Product {pid} added.");st.rerun()
                    except Exception as ex: st.error(str(ex))
    with tab2:
        st.dataframe(orders,use_container_width=True,hide_index=True,height=400)
        if can(user,"Administrator"):
            if not orders.empty:
                with st.expander("Update order status"):
                    with st.form("update_order_status"):
                        selected_order=st.selectbox("Order",orders.order_id.tolist())
                        new_order_status=st.selectbox("New order status",["Placed","Shipped","Delivered","Cancelled","Returned"])
                        if st.form_submit_button("Update order"):
                            conn.execute('UPDATE "Order" SET order_status=? WHERE order_id=?',(new_order_status,selected_order))
                            conn.execute("INSERT INTO AuditLog(actor,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",(user["username"],"UPDATE_STATUS","Order",selected_order,new_order_status,now_iso()))
                            conn.commit();st.success("Order status updated.");st.rerun()
            with st.form("new_order"):
                st.markdown("**Register order**")
                customers=read("SELECT customer_id,full_name FROM Customer ORDER BY full_name")
                pcat=read("SELECT product_id,product_name,unit_price FROM Product WHERE active=1 ORDER BY product_name")
                c1,c2=st.columns(2);cust_label=c1.selectbox("Customer",customers.apply(lambda r:f"{r.full_name} · {r.customer_id}",axis=1).tolist(),key="order_customer")
                prod_label=c2.selectbox("Product",pcat.apply(lambda r:f"{r.product_name} · {r.product_id}",axis=1).tolist(),key="order_product")
                qty=c1.number_input("Quantity",min_value=1,max_value=100,step=1);order_status=c2.selectbox("Order status",["Placed","Shipped","Delivered","Cancelled","Returned"])
                if st.form_submit_button("Create order",type="primary"):
                    try:
                        customer_id=customers.iloc[customers.apply(lambda r:f"{r.full_name} · {r.customer_id}",axis=1).tolist().index(cust_label)].customer_id
                        product=pcat.iloc[pcat.apply(lambda r:f"{r.product_name} · {r.product_id}",axis=1).tolist().index(prod_label)]
                        oid="ORD-"+pd.Timestamp.now().strftime("%Y%m%d%H%M%S%f")
                        conn.execute('INSERT INTO "Order"(order_id,customer_id,product_id,order_date,quantity,order_total,order_status) VALUES(?,?,?,?,?,?,?)',(oid,customer_id,product.product_id,now_iso(),int(qty),float(product.unit_price)*int(qty),order_status))
                        conn.execute("INSERT INTO AuditLog(actor,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",(user["username"],"CREATE","Order",oid,f"{product.product_name}; qty={qty}",now_iso()))
                        conn.commit();st.success(f"Order {oid} created.");st.rerun()
                    except Exception as ex: st.error(str(ex))

# ---------- SLA & escalations ----------
elif page == "SLA & Escalations":
    hero("SERVICE LEVEL CONTROL", "SLA & escalation centre", "Monitor response and resolution clocks. Run the rules engine to flag overdue cases and automatically escalate them.")
    if can(user,"Administrator","Agent"):
        if st.button("Run SLA evaluation now",type="primary"):
            result=evaluate_slas(conn,user["username"]);st.success(f"Evaluation complete · {result['breached']} new breach(es), {result['escalated']} escalation(s).")
    overview=read("SELECT s.clock_status,COUNT(*) cases FROM SLAClock s JOIN Complaint c USING(complaint_id) WHERE 1=1"+agent_filter+" GROUP BY s.clock_status",agent_params)
    cols=st.columns(4)
    for i,label in enumerate(["Active","Paused","Breached","Escalated"]):
        val=int(overview.loc[overview.clock_status==label,"cases"].sum()) if not overview.empty else 0
        with cols[i]: st.metric(label,val)
    data=read("""SELECT c.complaint_id,cu.full_name,c.priority_level,c.current_status,s.clock_status,s.response_due_at,s.first_response_at,s.resolution_due_at,s.resolved_at,s.paused_minutes
      FROM SLAClock s JOIN Complaint c USING(complaint_id) LEFT JOIN Customer cu USING(customer_id) WHERE 1=1"""+agent_filter+" ORDER BY CASE s.clock_status WHEN 'Escalated' THEN 1 WHEN 'Breached' THEN 2 WHEN 'Active' THEN 3 ELSE 4 END,s.resolution_due_at",agent_params)
    st.dataframe(data,use_container_width=True,hide_index=True,height=500)
    st.download_button("Export SLA register",data.to_csv(index=False),"sla_register.csv","text/csv")
    st.info("SLA clocks pause while a case is in 'Waiting for Customer'. Keep the separate ResolveIQ automation worker running; it evaluates SLA deadlines every 30 seconds and sends in-app notifications (plus email when SMTP is configured).")

# ---------- data quality ----------
elif page == "Data Quality":
    hero("TRUST & GOVERNANCE", "Data quality monitor", "Run live checks for duplicate complaints, missing required fields and inconsistent SLA chronology.")
    if st.button("Run live data quality scan",type="primary"):
        count=run_data_quality(conn,user["username"]);st.success(f"Scan finished. {count} potential issue(s) identified.")
    issues=read("SELECT issue_id,complaint_id,issue_type,ground_truth_label,description,detected,detected_at FROM AnomalyIssue ORDER BY detected DESC,issue_type")
    detected=int((issues.detected==1).sum()) if len(issues) else 0
    a,b,c=st.columns(3);a.metric("Issues in register",len(issues));b.metric("Detected",detected);c.metric("Undetected labels",len(issues)-detected)
    st.dataframe(issues,use_container_width=True,hide_index=True,height=440)
    fk=conn.execute("PRAGMA foreign_key_check").fetchall()
    st.metric("Database foreign-key violations",len(fk))
    st.download_button("Export issue register",issues.to_csv(index=False),"data_quality_issues.csv","text/csv")
    st.caption("Ground-truth labels are retained separately from live detections so model evaluation and operational findings are not confused.")

# ---------- reports ----------
elif page == "Reports & Analytics":
    hero("BUSINESS INTELLIGENCE", "Reports & analytics", "Explore category demand, service outcomes, team performance and customer experience indicators.")
    d1,d2=st.columns(2)
    with d1: start=st.date_input("Created from",value=pd.Timestamp.today().date()-pd.Timedelta(days=90))
    with d2: end=st.date_input("Created through",value=pd.Timestamp.today().date())
    report=read("SELECT c.*,k.category_name,cu.city FROM Complaint c LEFT JOIN Category k USING(category_id) LEFT JOIN Customer cu USING(customer_id) WHERE date(c.created_at) BETWEEN ? AND ?",(str(start),str(end)))
    a,b,c,d=st.columns(4);a.metric("Cases in period",len(report));b.metric("Critical / High",int(report.priority_level.isin(["Critical","High"]).sum()) if len(report) else 0);c.metric("Resolved",int(report.current_status.isin(["Resolved","Closed"]).sum()) if len(report) else 0);d.metric("Resolution rate",f"{(report.current_status.isin(['Resolved','Closed']).mean()*100):.1f}%" if len(report) else "0.0%")
    l,r=st.columns(2)
    with l:
        cat=report.groupby("category_name").size().reset_index(name="cases").sort_values("cases",ascending=False)
        st.plotly_chart(px.bar(cat,x="category_name",y="cases",title="Complaint demand by category",text_auto=True),use_container_width=True)
    with r:
        trend=report.assign(day=report.created_at.str[:10]).groupby("day").size().reset_index(name="cases")
        st.plotly_chart(px.line(trend,x="day",y="cases",markers=True,title="Daily complaint intake"),use_container_width=True)
    agent_perf=read("""SELECT a.agent_name,t.team_name,COUNT(DISTINCT x.complaint_id) assigned_cases,
      SUM(CASE WHEN c.current_status IN ('Resolved','Closed') THEN 1 ELSE 0 END) resolved_cases
      FROM Agent a JOIN Team t USING(team_id) LEFT JOIN Assignment x ON x.agent_id=a.agent_id AND x.is_current=1
      LEFT JOIN Complaint c USING(complaint_id) GROUP BY a.agent_id ORDER BY assigned_cases DESC""")
    st.markdown('<div class="section-head">Agent performance snapshot</div>',unsafe_allow_html=True);st.dataframe(agent_perf,use_container_width=True,hide_index=True)
    st.download_button("Download report dataset",report.to_csv(index=False),"complaint_analytics.csv","text/csv")

# ---------- administration ----------
elif page == "Administration":
    hero("PLATFORM GOVERNANCE", "Administration", "Manage application users and inspect the audit trail. Demo credentials must be changed before production use.")
    with st.expander("Create a user account",expanded=True):
        with st.form("create_user"):
            c1,c2=st.columns(2);uname=c1.text_input("Username");display=c2.text_input("Display name");pw=c1.text_input("Temporary password",type="password");role_new=c2.selectbox("Role",["Administrator","Agent","Analyst","Requester"])
            if st.form_submit_button("Create account",type="primary"):
                try: uid=create_user(conn,uname,pw,role_new,display,user["username"]);st.success(f"Created account {uid}");st.rerun()
                except Exception as ex: st.error(str(ex))
    users=read("SELECT user_id,username,role,display_name,active,created_at FROM AppUser ORDER BY created_at")
    st.markdown('<div class="section-head">Application users</div>',unsafe_allow_html=True);st.dataframe(users,use_container_width=True,hide_index=True)
    st.markdown('<div class="section-head">Audit trail · latest 500 events</div>',unsafe_allow_html=True)
    audit=read("SELECT created_at,actor,action,entity_type,entity_id,details FROM AuditLog ORDER BY audit_id DESC LIMIT 500")
    st.dataframe(audit,use_container_width=True,hide_index=True,height=420)
    st.download_button("Export audit log",audit.to_csv(index=False),"audit_log.csv","text/csv")

# ---------- data dictionary ----------
elif page == "Data Dictionary":
    hero("REFERENCE", "Data dictionary & business rules", "Understand the entities, relationships, classification logic and operational policies behind ResolveIQ.")
    st.markdown((Path(__file__).parent/"docs"/"data_dictionary.md").read_text(encoding="utf-8"))
    st.divider();st.markdown((Path(__file__).parent/"docs"/"business_rules.md").read_text(encoding="utf-8"))

conn.close()
