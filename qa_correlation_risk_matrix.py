"""
QA Test Suite for Feature 14: Institutional Correlation & Risk Clustering Terminal
"""

import unittest
import numpy as np
from src.correlation_service import CorrelationService


class TestCorrelationRiskMatrix(unittest.TestCase):

    def test_01_fallback_correlation_matrix_properties(self):
        """Verify correlation matrix symmetry, diagonal=1.0, and bounds [-1, 1]."""
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        names = {t: t for t in tickers}
        weights = {t: 0.25 for t in tickers}

        res = CorrelationService._generate_fallback_analysis(tickers, names, weights)
        matrix = res["matrix"]
        n = len(tickers)

        self.assertEqual(len(matrix), n)
        for i in range(n):
            self.assertEqual(len(matrix[i]), n)
            self.assertEqual(matrix[i][i], 1.0)
            for j in range(n):
                # Symmetry
                self.assertAlmostEqual(matrix[i][j], matrix[j][i], places=2)
                # Bounds
                self.assertGreaterEqual(matrix[i][j], -1.0)
                self.assertLessEqual(matrix[i][j], 1.0)

        # Diversification score must be in [0, 100]
        self.assertGreaterEqual(res["diversification_score"], 0)
        self.assertLessEqual(res["diversification_score"], 100)

        # Risk parity weights must sum to 100%
        rp_sum = sum(w["risk_parity_weight_pct"] for w in res["risk_parity_weights"])
        self.assertAlmostEqual(rp_sum, 100.0, places=0)

    def test_02_clustering_algorithm(self):
        """Verify clustering groups highly correlated assets together."""
        tickers = ["TECH1", "TECH2", "DEF1", "DEF2"]
        names = {t: t for t in tickers}

        # Fabricate correlation matrix where TECH1 & TECH2 are 0.90 correlated, and DEF1 & DEF2 are 0.85
        corr_mat = np.array([
            [1.0,  0.90, 0.10, 0.15],
            [0.90, 1.0,  0.12, 0.18],
            [0.10, 0.12, 1.0,  0.85],
            [0.15, 0.18, 0.85, 1.0]
        ])

        clusters = CorrelationService._cluster_assets(tickers, corr_mat, names)
        self.assertGreaterEqual(len(clusters), 1)

        # Find cluster with TECH1
        tech_cluster = next((c for c in clusters if "TECH1" in c["tickers"]), None)
        self.assertIsNotNone(tech_cluster)
        self.assertIn("TECH2", tech_cluster["tickers"])
        self.assertTrue(tech_cluster["is_tight_cluster"])

    def test_03_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/correlation and timeframe parameter."""
        import os
        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)
        pw = os.environ.get("APP_ACCESS_PASSWORD", "test-pass")
        client.post("/api/auth/login", json={"password": pw})

        pm = api.get_portfolio_manager()
        portfolios = pm.get_portfolios()
        if portfolios:
            p_id = portfolios[0]["id"]
            # 1. Default 1y
            resp = client.get(f"/api/portfolio/{p_id}/correlation")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("matrix", data)
            self.assertIn("diversification_score", data)
            self.assertIn("risk_clusters", data)

            # 2. Custom timeframe 90d
            resp_90d = client.get(f"/api/portfolio/{p_id}/correlation?timeframe=90d")
            self.assertEqual(resp_90d.status_code, 200)
            data_90d = resp_90d.json()
            self.assertEqual(data_90d["timeframe"], "90d")


if __name__ == "__main__":
    unittest.main()
