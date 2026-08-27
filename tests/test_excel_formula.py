from core.excel_writer import neutralize_excel_value


def test_formula_leaders_get_apostrophe():
    assert neutralize_excel_value("=cmd") == "'=cmd"
    assert neutralize_excel_value("+1+1") == "'+1+1"
    assert neutralize_excel_value("-2") == "'-2"
    assert neutralize_excel_value("@SUM(1)") == "'@SUM(1)"
    assert neutralize_excel_value("safe") == "safe"
    assert neutralize_excel_value(12) == 12
    assert neutralize_excel_value(None) is None
