"""WebDev Tool - Logika untuk inisialisasi proyek web/mobile."""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


FRAMEWORK_TEMPLATES = {
    "react": {
        "files": {
            "package.json": '{"name":"app","scripts":{"dev":"react-scripts start","build":"react-scripts build"}}',
            "src/App.js": 'import React from "react";\nexport default function App() { return <div>Hello React</div>; }',
            "src/index.js": 'import React from "react";\nimport ReactDOM from "react-dom";\nimport App from "./App";\nReactDOM.render(<App />, document.getElementById("root"));',
            "public/index.html": '<!DOCTYPE html><html><head><title>App</title></head><body><div id="root"></div></body></html>',
        },
        "dependencies": ["react", "react-dom", "react-scripts"],
    },
    "vue": {
        "files": {
            "package.json": '{"name":"app","scripts":{"dev":"vue-cli-service serve","build":"vue-cli-service build"}}',
            "src/App.vue": '<template><div>Hello Vue</div></template><script>export default { name: "App" }</script>',
            "src/main.js": 'import { createApp } from "vue";\nimport App from "./App.vue";\ncreateApp(App).mount("#app");',
        },
        "dependencies": ["vue"],
    },
    "flask": {
        "files": {
            "app.py": 'from flask import Flask\napp = Flask(__name__)\n\n@app.route("/")\ndef index():\n    return "Hello Flask"\n\nif __name__ == "__main__":\n    app.run(host="0.0.0.0", port=5000)',
            "templates/index.html": '<!DOCTYPE html><html><body><h1>Hello Flask</h1></body></html>',
        },
        "dependencies": ["flask"],
    },
    "express": {
        "files": {
            "package.json": '{"name":"app","scripts":{"start":"node server.js"}}',
            "server.js": 'const express = require("express");\nconst app = express();\napp.get("/", (req, res) => res.send("Hello Express"));\napp.listen(5000, "0.0.0.0");',
        },
        "dependencies": ["express"],
    },
    "nextjs": {
        "files": {
            "package.json": '{"name":"app","scripts":{"dev":"next dev","build":"next build"}}',
            "pages/index.js": 'export default function Home() { return <div>Hello Next.js</div>; }',
        },
        "dependencies": ["next", "react", "react-dom"],
    },
}


class WebDevTool:
    def __init__(self, default_port: int = 5000):
        self.default_port = default_port
        self.projects: list[dict] = []

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        return (
            f"WebDev tool siap. Intent: {intent}. "
            f"Framework tersedia: {', '.join(FRAMEWORK_TEMPLATES.keys())}. "
            f"Gunakan init_project() untuk memulai proyek baru."
        )

    def init_project(self, name: str, framework: str, output_dir: str = ".") -> dict:
        if framework not in FRAMEWORK_TEMPLATES:
            return {
                "success": False,
                "error": f"Framework '{framework}' tidak didukung. Pilih: {list(FRAMEWORK_TEMPLATES.keys())}",
            }

        template = FRAMEWORK_TEMPLATES[framework]
        project_dir = os.path.join(output_dir, name)
        os.makedirs(project_dir, exist_ok=True)

        created_files = []
        for file_path, content in template["files"].items():
            full_path = os.path.join(project_dir, file_path)
            os.makedirs(os.path.dirname(full_path) or project_dir, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            created_files.append(file_path)

        project_info = {
            "name": name,
            "framework": framework,
            "directory": project_dir,
            "files": created_files,
            "dependencies": template.get("dependencies", []),
        }
        self.projects.append(project_info)
        logger.info(f"Proyek '{name}' diinisialisasi dengan {framework}")

        return {"success": True, "project": project_info}

    def list_frameworks(self) -> list[str]:
        return list(FRAMEWORK_TEMPLATES.keys())

    def get_project_structure(self, project_dir: str) -> dict:
        structure = {"directories": [], "files": []}
        for root, dirs, files in os.walk(project_dir):
            rel_root = os.path.relpath(root, project_dir)
            for d in dirs:
                structure["directories"].append(os.path.join(rel_root, d))
            for f in files:
                structure["files"].append(os.path.join(rel_root, f))
        return structure
