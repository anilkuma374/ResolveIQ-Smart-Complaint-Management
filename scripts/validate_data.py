import sqlite3, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import DB_PATH

def validate():
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row
    fk=con.execute('PRAGMA foreign_key_check').fetchall()
    checks=[]
    checks.append({"check":"Foreign key integrity","passed":len(fk)==0,"detail":f"{len(fk)} violation(s)"})
    for table in ["Customer","Product","Order","Complaint","ComplaintMessage","Category","PriorityRule","Assignment","SLAClock","Resolution","Survey"]:
        n=con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        checks.append({"check":f"{table} populated","passed":n>0,"detail":f"{n} rows"})
    # These two checks are expected to identify deliberate labelled edge cases.
    bad_sla=con.execute("SELECT COUNT(*) FROM SLAClock WHERE pause_started_at IS NOT NULL AND resumed_at < pause_started_at").fetchone()[0]
    bad_res=con.execute("SELECT COUNT(*) FROM Resolution r JOIN Complaint c USING(complaint_id) WHERE r.resolved_at<c.created_at").fetchone()[0]
    expected_sla=con.execute("SELECT COUNT(*) FROM AnomalyIssue WHERE issue_type='invalid_sla_pause'").fetchone()[0]
    expected_res=con.execute("SELECT COUNT(*) FROM AnomalyIssue WHERE issue_type='resolution_before_complaint'").fetchone()[0]
    checks.append({"check":"SLA pause chronology accounted for","passed":bad_sla==expected_sla,"detail":f"{bad_sla} invalid pause(s), {expected_sla} labelled"})
    checks.append({"check":"Resolution chronology accounted for","passed":bad_res==expected_res,"detail":f"{bad_res} early resolution(s), {expected_res} labelled"})
    result={"passed":sum(x["passed"] for x in checks),"total":len(checks),"checks":checks}
    print(json.dumps(result,indent=2)); con.close(); return result
if __name__=="__main__": validate()
