"""Custom middleware for optional Agentation toolbar injection."""

from __future__ import annotations

from django.conf import settings

from agentation import AgentationConfig, inject_agentation, is_enabled


class AgentationDjangoMiddleware:
    """Inject Agentation toolbar into HTML responses in prototype/dev mode."""

    def __init__(self, get_response):
        self.get_response = get_response
        config_overrides = getattr(settings, 'AGENTATION_CONFIG', {})
        self.config = AgentationConfig(**config_overrides)
        self.enabled = is_enabled(self.config, framework_debug=getattr(settings, 'DEBUG', False))

    def __call__(self, request):
        response = self.get_response(request)
        if not self.enabled:
            return response

        if getattr(response, 'streaming', False):
            return response

        content_type = response.get('Content-Type', '')
        if 'text/html' not in content_type.lower():
            return response

        charset = getattr(response, 'charset', None) or 'utf-8'
        try:
            html = response.content.decode(charset)
        except Exception:
            return response

        injected_html = inject_agentation(html, self.config, route=request.path)
        if injected_html == html:
            return response

        response.content = injected_html.encode(charset)
        if response.has_header('Content-Length'):
            response['Content-Length'] = str(len(response.content))
        return response
