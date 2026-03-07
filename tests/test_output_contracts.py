from __future__ import annotations

import json
from pathlib import Path

from site_inspector.diffing import diff_runs
from tests.contract_assertions import assert_contract
from tests.helpers import run_cli, seed_resume_run


def _load_contract(name: str) -> dict:
    return json.loads((Path(__file__).parent / 'golden' / name).read_text(encoding='utf-8'))


def test_run_json_matches_contract(tmp_path: Path, fixture_site_url: str) -> None:
    out_dir = tmp_path / 'run'
    seed_resume_run(out_dir, fixture_site_url)
    result = run_cli(['run', f'{fixture_site_url}/index.html', '--resume', '--skip-playwright', '--out', str(out_dir)])
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads((out_dir / 'run.json').read_text(encoding='utf-8'))
    assert_contract(payload, _load_contract('run_contract.json'))


def test_quality_summary_matches_contract(tmp_path: Path, fixture_site_url: str) -> None:
    out_dir = tmp_path / 'run'
    seed_resume_run(out_dir, fixture_site_url)
    payload = json.loads((out_dir / 'quality_summary.json').read_text(encoding='utf-8'))
    assert_contract(payload, _load_contract('quality_summary_contract.json'))


def test_diff_json_matches_contract() -> None:
    run_a = {
        'generated_at': '2026-03-06T00:00:00Z',
        'target_url': 'https://example.com/',
        'crawl': {'pages': [{'url': 'https://example.com/'}, {'url': 'https://example.com/about'}]},
        'posture': {'fingerprinting': {'third_party_domains': ['cdn.example.net'], 'tech': {'wappalyzer': {'WordPress': {}}, 'builtwith': {'cms': ['WordPress']}}}},
        'quality': {'passed': True, 'pages_failed': 0, 'results': [{'url': 'https://example.com/', 'scores': {'performance': 0.9}, 'budget_eval': {'passed': True}}]},
        'playwright': None,
    }
    run_b = {
        'generated_at': '2026-03-07T00:00:00Z',
        'target_url': 'https://example.com/',
        'crawl': {'pages': [{'url': 'https://example.com/'}, {'url': 'https://example.com/contact'}]},
        'posture': {'fingerprinting': {'third_party_domains': ['cdn.example.net', 'analytics.example.net'], 'tech': {'wappalyzer': {'WordPress': {}, 'Nginx': {}}, 'builtwith': {'cms': ['WordPress'], 'web-servers': ['Nginx']}}}},
        'quality': {'passed': True, 'pages_failed': 0, 'results': [{'url': 'https://example.com/', 'scores': {'performance': 0.88}, 'budget_eval': {'passed': True}}]},
        'playwright': None,
    }
    payload = diff_runs(run_a, run_b, score_regression_threshold=0.05)
    assert_contract(payload, _load_contract('diff_contract.json'))
