"""PAT-only transport using the official Plane MCP implementation."""
import uvicorn
from plane_mcp.server import get_header_mcp

mcp = get_header_mcp()
app = mcp.http_app(path="/http/api-key/mcp", stateless_http=True)
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8211, access_log=False)
