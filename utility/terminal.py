try:
    from .agentToolKit import SiteTree
except ImportError:
    from agentToolKit import SiteTree

# Terminal class. MCP for agent / assistant ineraction with website. 
# Master control panel for all auth protected processes: login, payment, etc.
# TODO: Implement the actual terminal functionality, including command parsing and execution.
class Terminal:
    def __init__(self):
        self.tree = SiteTree()
        self.auth = "<auth_token>"
