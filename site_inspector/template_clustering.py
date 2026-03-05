
from urllib.parse import urlparse

def url_to_template(url: str) -> str:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]

    if not parts:
        return "/"

    if len(parts) == 1:
        return f"/{parts[0]}/*"

    return "/" + "/".join(parts[:-1]) + "/*"


def cluster_urls(urls):
    clusters = {}
    for url in urls:
        template = url_to_template(url)
        clusters.setdefault(template, []).append(url)
    return clusters


def summarize_clusters(clusters):
    summary = []
    for template, pages in sorted(clusters.items(), key=lambda x: -len(x[1])):
        summary.append({
            "template": template,
            "pages": len(pages)
        })
    return summary
