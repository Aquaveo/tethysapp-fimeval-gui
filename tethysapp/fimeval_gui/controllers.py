from tethys_sdk.routing import controller


@controller(login_required=False)
def home(request):
    """Controller for the app home page (SPA catch-all)."""
    from tethysapp.fimeval_gui.app import App  # lazy import
    return App.render(request, 'index.html')
