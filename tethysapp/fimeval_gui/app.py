from tethys_sdk.base import TethysAppBase


class App(TethysAppBase):
    """FIMeval GUI Tethys App."""

    name = 'FIMeval GUI'
    package = 'fimeval_gui'
    root_url = 'fimeval-gui'
    index = 'home'
    catch_all = 'home'

    description = 'Webapp GUI for the FIMeval flood inundation map evaluation framework'
    color = '#007bff'
    tags = 'FIM, Flood Mapping, Flood Inundation Mapping, Hydrology, Evaluation, GIS'
    enable_feedback = False
    feedback_emails = []
