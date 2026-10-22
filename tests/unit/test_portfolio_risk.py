from decimal import Decimal

from private_trading_risk.portfolio import (
    OpenExposure,
    PortfolioRiskInput,
    PortfolioRiskPolicy,
    assess_portfolio_risk,
    specialist_risk_pct,
)


def test_portfolio_blocks_duplicate_and_correlated_crypto_risk() -> None:
    result = assess_portfolio_risk(
        PortfolioRiskInput(
            proposed_symbol="BTC/USDT",
            proposed_asset_class="crypto",
            proposed_direction="long",
            proposed_risk_pct=Decimal("0.5"),
            open_exposures=(
                OpenExposure("BTC/USDT", "crypto", "long", Decimal("0.4")),
                OpenExposure("ETH/USDT", "crypto", "long", Decimal("0.3")),
            ),
        )
    )
    assert result.approved is False
    assert "symbol_already_open" in result.blockers
    assert "crypto_cluster_risk_exceeded" in result.blockers


def test_portfolio_blocks_clustered_usd_forex_and_daily_loss() -> None:
    result = assess_portfolio_risk(
        PortfolioRiskInput(
            proposed_symbol="GBP/USD",
            proposed_asset_class="forex",
            proposed_direction="long",
            proposed_risk_pct=Decimal("0.5"),
            open_exposures=(
                OpenExposure("EUR/USD", "forex", "long", Decimal("0.6")),
            ),
            daily_realized_pnl_pct=Decimal("-1.5"),
        )
    )
    assert result.approved is False
    assert "usd_cluster_risk_exceeded" in result.blockers
    assert "daily_loss_stop" in result.blockers


def test_specialist_sizing_is_small_and_zero_without_edge() -> None:
    assert (
        specialist_risk_pct(objective="profit", mean_r=-0.01, max_drawdown_r=2)
        == 0
    )
    sized = specialist_risk_pct(
        objective="profit",
        mean_r=0.2,
        max_drawdown_r=10,
    )
    assert Decimal("0.1") <= sized <= Decimal("0.5")


def test_custom_policy_can_approve_diversified_exposure() -> None:
    result = assess_portfolio_risk(
        PortfolioRiskInput(
            proposed_symbol="EUR/GBP",
            proposed_asset_class="forex",
            proposed_direction="short",
            proposed_risk_pct=Decimal("0.25"),
        ),
        PortfolioRiskPolicy(max_total_open_risk_pct=Decimal("1")),
    )
    assert result.approved is True
