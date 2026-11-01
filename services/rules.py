from datetime import datetime, timedelta

CATEGORY_RULES = [
 ("Product Safety", ["overheat","smoke","fire","electric shock","injury","safety hazard"], "Safety", "Critical"),
 ("Product Defect", ["broken","defective","not working","malfunction","damaged"], "Technical Support", "High"),
 ("Refund", ["refund","money back","reimbursement"], "Billing", "Moderate"),
 ("Payment", ["payment","charged","invoice","transaction"], "Billing", "Moderate"),
 ("Delivery", ["late","delayed","delivery","courier","shipment"], "Logistics", "Moderate"),
 ("Warranty", ["warranty","repair","replacement"], "Technical Support", "Moderate"),
 ("Account", ["login","password","account"], "Customer Care", "Low"),
 ("Cancellation", ["cancel","cancellation"], "Order Management", "Low"),
 ("Service", ["rude","poor service","unhelpful","staff"], "Customer Care", "Moderate"),
]
CATEGORIES = ["Product Safety","Product Defect","Delivery","Refund","Payment","Account","Warranty","Service","Cancellation","Other"]
TEAMS = ["Safety","Technical Support","Logistics","Billing","Customer Care","Order Management"]
SLA_HOURS = {"Critical":(0.25,4),"High":(1,24),"Medium":(4,72),"Low":(8,120)}

def classify(description):
    t=(description or "").lower()
    for category,words,team,severity in CATEGORY_RULES:
        if any(w in t for w in words):
            return category,severity
    return "Other","Low"

def determine_priority(category,severity,sentiment,order_value,recurrence,vulnerable=False):
    if category=="Product Safety" or severity=="Critical": return "Critical"
    if recurrence>=3: return "Critical" if sentiment<=-0.8 else "High"
    if vulnerable and sentiment<-.35: return "High"
    if severity=="High" or (order_value>=50000 and sentiment<-.35): return "High"
    if sentiment<=-.75: return "High"
    if severity=="Moderate" or recurrence==2 or order_value>=25000: return "Medium"
    return "Low"

def team_for_category(category):
    for cat,words,team,severity in CATEGORY_RULES:
        if cat==category: return team
    return "Customer Care"

def sla_deadlines(created_at,priority):
    created=datetime.fromisoformat(created_at)
    response,resolution=SLA_HOURS[priority]
    return ((created+timedelta(hours=response)).isoformat(timespec="seconds"),
            (created+timedelta(hours=resolution)).isoformat(timespec="seconds"))
