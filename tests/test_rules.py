from services.rules import classify, determine_priority, sla_deadlines
from datetime import datetime

def test_safety_classification():
    assert classify("Device overheating and smoke detected")[0] == "Product Safety"

def test_safety_override():
    assert determine_priority("Product Safety","Critical",0.5,100,1,False) == "Critical"

def test_sla_order():
    response,resolution=sla_deadlines("2026-10-22T10:00:00","Critical")
    assert datetime.fromisoformat(response) < datetime.fromisoformat(resolution)
