"""Local decorative SVG assets for the dashboard presentation layer."""
import base64

PATHS = {
    'image': '<rect x="3" y="3" width="26" height="26" rx="3"/><circle cx="11" cy="11" r="2"/><path d="m4 24 8-9 5 5 5-8 7 9"/>',
    'camera': '<rect x="2" y="6" width="19" height="20" rx="3"/><path d="m21 12 9-5v18l-9-5"/>',
    'record': '<rect x="5" y="2" width="22" height="28" rx="3"/><path d="M10 9h12M10 15h12M10 21h7"/>',
    'analysis': '<path d="M4 28V17h4v11M14 28V9h4v19M24 28V3h4v25"/>',
    'target': '<circle cx="16" cy="16" r="6"/><path d="M16 2v4M16 26v4M2 16h4M26 16h4M6 6a14 14 0 0 1 20 0M6 26a14 14 0 0 1 0-20M26 6a14 14 0 0 1 0 20M6 26a14 14 0 0 0 20 0"/>',
    'question': '<circle cx="16" cy="16" r="13"/><path d="M12 11a4 4 0 1 1 7 3c-2 1-3 2-3 5M16 23v1"/>',
    'bulb': '<path d="M10 23c0-5-5-5-5-12a11 11 0 0 1 22 0c0 7-5 7-5 12zM11 27h10M14 30h4"/>',
    'play': '<path d="m10 5 17 11-17 11z"/>',
    'download': '<path d="M16 2v19m-7-7 7 7 7-7M4 22v7h24v-7"/>',
    'person': '<circle cx="16" cy="11" r="8"/><path d="M3 30c0-12 26-12 26 0M11 18l5 5 5-5"/>',
    'warning': '<path d="M14 3a2 2 0 0 1 4 0l13 24a2 2 0 0 1-2 3H3a2 2 0 0 1-2-3zM16 11v9M16 24v1"/>',
    'helmet': '<path d="M7 7 12 2h12l5 6-2 15-11 7-10-7zM10 9l15 2-2 8-14-2zM5 10 2 23l7 5"/>',
}


def svg_url(body, viewbox='0 0 32 32'):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()


def icon_url(name):
    return svg_url(PATHS[name])


def icon_html(name):
    return f'<span class="dash-icon" aria-hidden="true" style="--icon:url({icon_url(name)})"></span>'
