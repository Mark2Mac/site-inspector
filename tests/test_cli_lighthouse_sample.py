from __future__ import annotations

from pathlib import Path

from site_inspector import cli


class _Args:
    target = 'https://example.com'
    max_pages = 5
    timeout = 5
    crawl_workers = 1
    net_workers = None
    lighthouse_workers = 1
    lighthouse_sample = 2
    lighthouse_per_group = 1
    lighthouse_max_pages = None
    lighthouse_include = None
    playwright_workers = 1
    skip_playwright = True
    budget = None
    resume = False
    out = None


def test_cmd_run_lighthouse_sample_uses_group_map_without_name_error(tmp_path: Path, monkeypatch) -> None:
    args = _Args()
    args.out = str(tmp_path / 'run')

    crawl = {
        'pages': [
            {'url': 'https://example.com/', 'dom_fingerprint': 'fp-home'},
            {'url': 'https://example.com/about', 'dom_fingerprint': 'fp-a'},
            {'url': 'https://example.com/contact', 'dom_fingerprint': 'fp-b'},
        ]
    }

    seen: dict[str, object] = {}

    monkeypatch.setattr(cli, 'discover_pages', lambda *a, **k: crawl)
    monkeypatch.setattr(cli, 'collect_posture', lambda *a, **k: {'ok': True})

    def fake_select(urls, **kwargs):
        seen['group_map'] = kwargs.get('group_map')
        return {'selected_urls': list(urls)[:2], 'selection': {'mode': 'sampled'}}

    monkeypatch.setattr(cli, 'select_lighthouse_targets', fake_select)
    monkeypatch.setattr(cli, 'quality_for_urls', lambda *a, **k: {'generated_at': 'x', 'pages_tested': 0, 'pages_failed': 0, 'passed': True, 'budget': {}, 'lighthouse_workers': 1, 'results': [], 'failures': []})
    monkeypatch.setattr(cli, 'audit_seo', lambda *a, **k: {'pages_analyzed': 0, 'issues': []})
    monkeypatch.setattr(cli, 'audit_ai_readiness', lambda *a, **k: {'pages_analyzed': 0, 'issues': []})

    rc = cli.cmd_run(args)
    assert rc == 0
    assert isinstance(seen.get('group_map'), dict)
    assert seen['group_map']['https://example.com/about'] == 'dom:fp-a'
