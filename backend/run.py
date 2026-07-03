import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("QA_AGENT_PORT", "8756"))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)
