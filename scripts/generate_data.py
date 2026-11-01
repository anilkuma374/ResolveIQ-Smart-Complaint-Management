import argparse, csv, json, random, sqlite3, hashlib, sys
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import DB_PATH, EXPORT_DIR, GROUND_TRUTH_DIR, SCHEMA_PATH
from services.rules import classify, determine_priority, sla_deadlines, CATEGORIES, team_for_category

FIRST=["Aarav","Aditi","Arjun","Diya","Ishaan","Kavya","Meera","Neha","Rohan","Sana","Vihaan","Anaya","Kabir","Mira","Dev","Tara"]
LAST=["Sharma","Reddy","Patel","Kumar","Iyer","Gupta","Rao","Nair","Das","Singh","Mehta","Joshi"]
CITIES=["Hyderabad","Bengaluru","Mumbai","Chennai","Pune","Delhi","Kolkata","Jaipur"]
PRODUCTS=[("Smartphone X","Electronics",42000,1),("Laptop Pro","Electronics",78000,0),("Refrigerator 300L","Appliances",52000,1),("Washing Machine","Appliances",34000,0),("Wireless Earbuds","Electronics",4500,0),("Air Purifier","Appliances",18000,0),("Smart Watch","Electronics",12000,0),("Mixer Grinder","Appliances",6500,0)]
CHANNELS=["Email","Phone","Web","Mobile App","Social Media","Support Portal"]
ISSUES=[
 "Delivery is delayed and courier tracking has not updated.",
 "I want a refund because the payment was charged twice.",
 "The product is broken and not working properly.",
 "My device is overheating and smoke is coming from it; this is a safety hazard.",
 "I cannot log in to my account after resetting my password.",
 "The support staff were rude and unhelpful.",
 "Please help with warranty repair and replacement.",
 "I need to cancel my order before dispatch.",
 "The invoice shows an incorrect payment amount.",
 "The package arrived late and the item was damaged."
]
def iso(d): return d.replace(microsecond=0).isoformat()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--seed',type=int,default=20261022)
    ap.add_argument('--scale',type=float,default=1.0)
    a=ap.parse_args()
    if a.scale<=0: raise SystemExit("scale must be > 0")
    rng=random.Random(a.seed)
    counts={k:max(1,round(v*a.scale)) for k,v in {"customers":5000,"orders":8000,"complaints":2000,"messages":6000}.items()}
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    if DB_PATH.exists(): DB_PATH.unlink()
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row; con.execute('PRAGMA foreign_keys=ON')
    con.executescript(SCHEMA_PATH.read_text())
    cur=con.cursor(); base=datetime(2026,10,22,12)
    categories=[
      ("Product Safety","Safety concern: overheating, smoke, fire, shock, injury","Safety"),
      ("Product Defect","Damaged, defective, broken, malfunction","Technical Support"),
      ("Delivery","Late, delayed, missing delivery, courier","Logistics"),
      ("Refund","Refund and reimbursement","Billing"),("Payment","Payment and invoice","Billing"),
      ("Account","Login and profile access","Customer Care"),("Warranty","Warranty repair","Technical Support"),
      ("Service","Customer service experience","Customer Care"),("Cancellation","Order cancellation","Order Management"),
      ("Other","Other complaint","Customer Care")]
    for i,x in enumerate(categories,1): cur.execute('INSERT INTO Category VALUES (?,?,?,?)',(f"CAT-{i:03d}",*x))
    rules=[("safety","true","Critical"),("severity","Critical","Critical"),("recurrence","3+","High"),("vulnerable","negative","High"),("value","50000+","High"),("sentiment","very negative","High")]
    for i,(k,v,p) in enumerate(rules,1): cur.execute('INSERT INTO PriorityRule VALUES (?,?,?,?,?,?,?,?,1)',(f"PR-{i:03d}",f"Priority rule {i}",k,v,p,i,iso(base-timedelta(days=365)),None))
    teams=["Safety","Technical Support","Logistics","Billing","Customer Care","Order Management"]
    for i,t in enumerate(teams,1): cur.execute('INSERT INTO Team VALUES (?,?)',(f"TEAM-{i:03d}",t))
    for i in range(1,31):
        tid=f"TEAM-{((i-1)%6)+1:03d}"
        cur.execute('INSERT INTO Agent VALUES (?,?,?,1)',(f"AGT-{i:04d}",f"Agent {i:02d}",tid))
    for i,p in enumerate(PRODUCTS,1): cur.execute('INSERT INTO Product VALUES (?,?,?,?,?,1)',(f"PRD-{i:04d}",*p))
    for i in range(1,counts["customers"]+1):
        name=f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        cur.execute('INSERT INTO Customer VALUES (?,?,?,?,?,?,?)',(f"CUS-{i:06d}",name,f"customer{i:06d}@example.test",f"+91-9{rng.randrange(100000000,999999999)}",rng.choice(CITIES),int(rng.random()<.06),iso(base-timedelta(days=rng.randint(30,1000)))))
    for i in range(1,counts["orders"]+1):
        cid=f"CUS-{rng.randint(1,counts['customers']):06d}"; pid=f"PRD-{rng.randint(1,len(PRODUCTS)):04d}"
        price=cur.execute('SELECT unit_price FROM Product WHERE product_id=?',(pid,)).fetchone()[0]
        qty=rng.randint(1,3)
        cur.execute('INSERT INTO "Order" VALUES (?,?,?,?,?,?,?)',(f"ORD-2026-{i:06d}",cid,pid,iso(base-timedelta(days=rng.randint(1,365))),qty,round(price*qty,2),rng.choice(["Placed","Shipped","Delivered","Delivered","Returned"])))
    complaint_ids=[]
    for i in range(1,counts["complaints"]+1):
        cid=f"CUS-{rng.randint(1,counts['customers']):06d}"; oid=f"ORD-2026-{rng.randint(1,counts['orders']):06d}"
        order=cur.execute('SELECT product_id,order_total FROM "Order" WHERE order_id=?',(oid,)).fetchone()
        desc=rng.choice(ISSUES); cat,sev=classify(desc); catid=cur.execute('SELECT category_id FROM Category WHERE category_name=?',(cat,)).fetchone()[0]
        sentiment=round(rng.uniform(-.95,.45),2); rec=rng.choices([1,2,3],[.78,.17,.05])[0]
        vuln=cur.execute('SELECT vulnerable_customer FROM Customer WHERE customer_id=?',(cid,)).fetchone()[0]
        priority=determine_priority(cat,sev,sentiment,order["order_total"],rec,bool(vuln))
        created=base-timedelta(days=rng.randint(0,90),hours=rng.randint(0,23)); comp=f"CMP-2026-{i:06d}"; complaint_ids.append(comp)
        status=rng.choices(["New","Assigned","In Progress","Waiting for Customer","Resolved","Closed","Reopened"],[.08,.15,.18,.10,.18,.27,.04])[0]
        cur.execute('INSERT INTO Complaint VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(comp,cid,oid,order["product_id"],rng.choice(CHANNELS),desc,catid,sev,sentiment,order["order_total"],rec,priority,status,iso(created),iso(created+timedelta(hours=rng.randint(0,48)))))
        rd,xd=sla_deadlines(iso(created),priority); resolved=created+timedelta(hours=rng.randint(1,100)) if status in ("Resolved","Closed") else None
        cur.execute('INSERT INTO SLAClock VALUES (?,?,?,?,?,?,?,?,?,?)',(f"SLA-{comp}",comp,rd,xd,None,iso(resolved) if resolved else None,"Completed" if resolved else "Active",0,None,None))
        team=team_for_category(cat); tid=cur.execute('SELECT team_id FROM Team WHERE team_name=?',(team,)).fetchone()[0]
        aid=cur.execute('SELECT agent_id FROM Agent WHERE team_id=? ORDER BY agent_id LIMIT 1',(tid,)).fetchone()[0]
        cur.execute('INSERT INTO Assignment VALUES (?,?,?,?,?,?,?,1)',(f"ASN-{comp}-001",comp,tid,aid,iso(created),"System","Category-based assignment"))
        cur.execute('INSERT INTO StatusEvent VALUES (?,?,?,?,?,?,?)',(f"EV-{comp}-001",comp,None,"New",iso(created),"System","Complaint created"))
        if status!="New": cur.execute('INSERT INTO StatusEvent VALUES (?,?,?,?,?,?,?)',(f"EV-{comp}-002",comp,"New",status,iso(created+timedelta(hours=1)),"System","Synthetic status progression"))
        if resolved:
            cur.execute('INSERT INTO Resolution VALUES (?,?,?,?,?,?,?)',(f"RES-{comp}",comp,rng.choice(["Replacement","Refund","Repair","Explanation","Credit"]),"Issue investigated and resolution provided.",round(rng.uniform(0,min(5000,order["order_total"])),2),iso(resolved),aid))
        if status=="Closed" and resolved:
            cur.execute('INSERT INTO Survey VALUES (?,?,?,?,?,?)',(f"SRV-{comp}",comp,iso(resolved+timedelta(hours=1)),iso(resolved+timedelta(hours=25)),rng.randint(2,5),"Synthetic post-resolution feedback"))
    message_seq={}
    for j in range(1,counts["messages"]+1):
        comp=complaint_ids[(j-1)%len(complaint_ids)]
        message_seq[comp]=message_seq.get(comp,0)+1
        created=datetime.fromisoformat(cur.execute('SELECT created_at FROM Complaint WHERE complaint_id=?',(comp,)).fetchone()[0])+timedelta(minutes=10*j)
        sender=rng.choice(["Customer","Agent","System"])
        cur.execute('INSERT INTO ComplaintMessage VALUES (?,?,?,?,?,?,?,?)',(f"MSG-{comp}-{message_seq[comp]:03d}",comp,sender,None,rng.choice(CHANNELS),"Synthetic message: customer update or agent response.",iso(created),int(sender!="Agent" or rng.random()<.8)))
    # Explicit labelled negative scenarios.
    edge=[
      ("missing_customer","Complaint without customer","CMP-2026-000001","Customer reference is missing."),
      ("resolution_before_complaint","Resolution before complaint","CMP-2026-000002","Resolution timestamp precedes complaint creation."),
      ("invalid_sla_pause","SLA clock pauses incorrectly","CMP-2026-000003","Resume timestamp precedes pause start."),
      ("repeat_issue_unlinked","Repeat issue not linked","CMP-2026-000004","Recurrence exists but related complaint link is absent."),
      ("critical_in_low_queue","Critical safety issue assigned to low-priority queue","CMP-2026-000005","Critical safety issue routed to Customer Care."),
      ("survey_before_closure","Survey before closure","CMP-2026-000006","Survey sent before closure.")
    ]
    for typ,label,cid,desc in edge:
        if cid not in complaint_ids: continue
        row=cur.execute('SELECT created_at FROM Complaint WHERE complaint_id=?',(cid,)).fetchone(); t=datetime.fromisoformat(row[0])
        if typ=="missing_customer": cur.execute('UPDATE Complaint SET customer_id=NULL WHERE complaint_id=?',(cid,))
        elif typ=="resolution_before_complaint": cur.execute('INSERT OR REPLACE INTO Resolution VALUES (?,?,?,?,?,?,?)',(f"RES-{cid}",cid,"Refund","Injected chronology anomaly.",0,iso(t-timedelta(hours=2)),"AGT-0001"))
        elif typ=="invalid_sla_pause": cur.execute("UPDATE SLAClock SET clock_status='Paused',pause_started_at=?,resumed_at=?,paused_minutes=60 WHERE complaint_id=?",(iso(t+timedelta(hours=3)),iso(t+timedelta(hours=2)),cid))
        elif typ=="repeat_issue_unlinked": cur.execute('UPDATE Complaint SET recurrence_count=3 WHERE complaint_id=?',(cid,))
        elif typ=="critical_in_low_queue":
            catid=cur.execute("SELECT category_id FROM Category WHERE category_name='Product Safety'").fetchone()[0]
            cur.execute("UPDATE Complaint SET category_id=?,severity='Critical',priority_level='Critical',description='Product overheating with smoke and safety hazard.' WHERE complaint_id=?",(catid,cid))
            tid=cur.execute("SELECT team_id FROM Team WHERE team_name='Customer Care'").fetchone()[0]
            aid=cur.execute("SELECT agent_id FROM Agent WHERE team_id=? ORDER BY agent_id LIMIT 1",(tid,)).fetchone()[0]
            cur.execute("UPDATE Assignment SET team_id=?,agent_id=? WHERE complaint_id=?",(tid,aid,cid))
        elif typ=="survey_before_closure": cur.execute('INSERT OR REPLACE INTO Survey VALUES (?,?,?,?,?,?)',(f"SRV-{cid}",cid,iso(t-timedelta(hours=1)),None,None,"Injected pre-closure survey"))
        cur.execute('INSERT INTO AnomalyIssue VALUES (?,?,?,?,?,?,?)',(f"ISS-{cid}",cid,typ,label,desc,0,None))
    con.commit()
    tables=["Customer","Product","Order","Category","PriorityRule","Team","Agent","Complaint","ComplaintMessage","Assignment","SLAClock","Resolution","Survey","StatusEvent","SLAEvent","AnomalyIssue"]
    EXPORT_DIR.mkdir(parents=True,exist_ok=True); GROUND_TRUTH_DIR.mkdir(parents=True,exist_ok=True)
    for table in tables:
        rows=con.execute(f'SELECT * FROM "{table}"').fetchall()
        cols=[d[0] for d in con.execute(f'SELECT * FROM "{table}"').description]
        with open(EXPORT_DIR/(table.lower()+".csv"),"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f); w.writerow(cols); w.writerows([tuple(r) for r in rows])
        (EXPORT_DIR/(table.lower()+".json")).write_text(json.dumps([dict(r) for r in rows],indent=2),encoding="utf-8")
    truth=[{"issue_type":x[0],"ground_truth_label":x[1],"complaint_id":x[2],"description":x[3]} for x in edge]
    with open(GROUND_TRUTH_DIR/"ground_truth.csv","w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(truth[0])); w.writeheader(); w.writerows(truth)
    (GROUND_TRUTH_DIR/"ground_truth.json").write_text(json.dumps(truth,indent=2),encoding="utf-8")
    con.close()
    manifest={"seed":a.seed,"scale":a.scale,"counts":counts,"edge_case_count":len(truth),"checksums":{}}
    for p in sorted(EXPORT_DIR.glob("*.csv")): manifest["checksums"][p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    (EXPORT_DIR/"source_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(manifest,indent=2))
if __name__=="__main__": main()
