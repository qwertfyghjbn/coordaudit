from jinja2 import Environment

_env = Environment()


def render_report_template(title: str) -> str:
    template_str = "<h1>" + title + "</h1><p>Report Preview</p>"
    template = _env.from_string(template_str)
    return template.render()
