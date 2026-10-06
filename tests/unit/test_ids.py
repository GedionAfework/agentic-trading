from private_trading_core.ids import new_correlation_id, new_id


def test_new_id_is_uuid() -> None:
    value = new_id()
    assert value.version in {4, 7}


def test_correlation_id_is_string() -> None:
    cid = new_correlation_id()
    assert isinstance(cid, str)
    assert len(cid) > 0
