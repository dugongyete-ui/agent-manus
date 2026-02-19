"""WebDev Tool - Inisialisasi proyek web dan manajemen dependensi."""

import asyncio
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


FRAMEWORK_TEMPLATES = {
    "react": {
        "files": {
            "package.json": json.dumps({
                "name": "app",
                "version": "1.0.0",
                "private": True,
                "scripts": {
                    "dev": "react-scripts start",
                    "build": "react-scripts build",
                    "test": "react-scripts test",
                },
                "dependencies": {
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0",
                    "react-scripts": "5.0.1",
                },
            }, indent=2),
            "src/App.js": 'import React from "react";\n\nexport default function App() {\n  return (\n    <div className="App">\n      <h1>Hello React</h1>\n    </div>\n  );\n}\n',
            "src/index.js": 'import React from "react";\nimport ReactDOM from "react-dom/client";\nimport App from "./App";\n\nconst root = ReactDOM.createRoot(document.getElementById("root"));\nroot.render(<App />);\n',
            "public/index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>React App</title>\n</head>\n<body>\n  <div id="root"></div>\n</body>\n</html>\n',
        },
        "dependencies": ["react", "react-dom", "react-scripts"],
        "manager": "npm",
        "dev_command": "npm start",
        "build_command": "npm run build",
    },
    "vue": {
        "files": {
            "package.json": json.dumps({
                "name": "app",
                "version": "1.0.0",
                "private": True,
                "scripts": {
                    "dev": "vite",
                    "build": "vite build",
                    "preview": "vite preview",
                },
                "dependencies": {"vue": "^3.3.0"},
                "devDependencies": {"@vitejs/plugin-vue": "^4.0.0", "vite": "^5.0.0"},
            }, indent=2),
            "src/App.vue": '<template>\n  <div id="app">\n    <h1>Hello Vue</h1>\n  </div>\n</template>\n\n<script>\nexport default {\n  name: "App",\n};\n</script>\n',
            "src/main.js": 'import { createApp } from "vue";\nimport App from "./App.vue";\n\ncreateApp(App).mount("#app");\n',
            "index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>Vue App</title>\n</head>\n<body>\n  <div id="app"></div>\n  <script type="module" src="/src/main.js"></script>\n</body>\n</html>\n',
            "vite.config.js": 'import { defineConfig } from "vite";\nimport vue from "@vitejs/plugin-vue";\n\nexport default defineConfig({\n  plugins: [vue()],\n});\n',
        },
        "dependencies": ["vue"],
        "manager": "npm",
        "dev_command": "npm run dev",
        "build_command": "npm run build",
    },
    "flask": {
        "files": {
            "app.py": 'from flask import Flask, render_template, jsonify\n\napp = Flask(__name__)\n\n\n@app.route("/")\ndef index():\n    return render_template("index.html")\n\n\n@app.route("/api/health")\ndef health():\n    return jsonify({"status": "ok"})\n\n\nif __name__ == "__main__":\n    app.run(host="0.0.0.0", port=5000, debug=True)\n',
            "templates/index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>Flask App</title>\n</head>\n<body>\n  <h1>Hello Flask</h1>\n</body>\n</html>\n',
            "requirements.txt": "flask>=3.0.0\ngunicorn>=21.2.0\n",
        },
        "dependencies": ["flask", "gunicorn"],
        "manager": "pip",
        "dev_command": "python app.py",
        "build_command": None,
    },
    "express": {
        "files": {
            "package.json": json.dumps({
                "name": "app",
                "version": "1.0.0",
                "scripts": {
                    "start": "node server.js",
                    "dev": "node --watch server.js",
                },
                "dependencies": {"express": "^4.18.0"},
            }, indent=2),
            "server.js": 'const express = require("express");\nconst path = require("path");\n\nconst app = express();\nconst PORT = process.env.PORT || 5000;\n\napp.use(express.json());\napp.use(express.static("public"));\n\napp.get("/api/health", (req, res) => {\n  res.json({ status: "ok" });\n});\n\napp.get("/", (req, res) => {\n  res.sendFile(path.join(__dirname, "public", "index.html"));\n});\n\napp.listen(PORT, "0.0.0.0", () => {\n  console.log(`Server running on port ${PORT}`);\n});\n',
            "public/index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>Express App</title>\n</head>\n<body>\n  <h1>Hello Express</h1>\n</body>\n</html>\n',
        },
        "dependencies": ["express"],
        "manager": "npm",
        "dev_command": "npm run dev",
        "build_command": None,
    },
    "nextjs": {
        "files": {
            "package.json": json.dumps({
                "name": "app",
                "version": "1.0.0",
                "private": True,
                "scripts": {
                    "dev": "next dev",
                    "build": "next build",
                    "start": "next start",
                },
                "dependencies": {
                    "next": "^14.0.0",
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0",
                },
            }, indent=2),
            "app/page.js": 'export default function Home() {\n  return (\n    <main>\n      <h1>Hello Next.js</h1>\n    </main>\n  );\n}\n',
            "app/layout.js": 'export const metadata = {\n  title: "Next.js App",\n  description: "Created with Next.js",\n};\n\nexport default function RootLayout({ children }) {\n  return (\n    <html lang="en">\n      <body>{children}</body>\n    </html>\n  );\n}\n',
        },
        "dependencies": ["next", "react", "react-dom"],
        "manager": "npm",
        "dev_command": "npm run dev",
        "build_command": "npm run build",
    },
    "fastapi": {
        "files": {
            "main.py": 'from fastapi import FastAPI\nfrom fastapi.responses import HTMLResponse\n\napp = FastAPI()\n\n\n@app.get("/", response_class=HTMLResponse)\nasync def root():\n    return "<h1>Hello FastAPI</h1>"\n\n\n@app.get("/api/health")\nasync def health():\n    return {"status": "ok"}\n',
            "requirements.txt": "fastapi>=0.100.0\nuvicorn[standard]>=0.23.0\n",
        },
        "dependencies": ["fastapi", "uvicorn[standard]"],
        "manager": "pip",
        "dev_command": "uvicorn main:app --host 0.0.0.0 --port 5000 --reload",
        "build_command": None,
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

        gitignore_content = self._generate_gitignore(framework)
        gitignore_path = os.path.join(project_dir, ".gitignore")
        with open(gitignore_path, "w") as f:
            f.write(gitignore_content)
        created_files.append(".gitignore")

        project_info = {
            "name": name,
            "framework": framework,
            "directory": project_dir,
            "files": created_files,
            "dependencies": template.get("dependencies", []),
            "manager": template.get("manager", "npm"),
            "dev_command": template.get("dev_command"),
            "build_command": template.get("build_command"),
        }
        self.projects.append(project_info)
        logger.info(f"Proyek '{name}' diinisialisasi dengan {framework}")

        return {"success": True, "project": project_info}

    async def install_dependencies(self, project_dir: str, manager: str = "npm") -> dict:
        try:
            if manager == "npm":
                cmd = "npm install"
            elif manager == "yarn":
                cmd = "yarn install"
            elif manager == "pip":
                req_file = os.path.join(project_dir, "requirements.txt")
                if os.path.exists(req_file):
                    cmd = f"pip install -r {req_file}"
                else:
                    return {"success": False, "error": "requirements.txt tidak ditemukan"}
            else:
                return {"success": False, "error": f"Manager tidak didukung: {manager}"}

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            success = process.returncode == 0

            return {
                "success": success,
                "manager": manager,
                "output": stdout.decode("utf-8", errors="replace")[:3000],
                "errors": stderr.decode("utf-8", errors="replace")[:1000] if not success else None,
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": "Instalasi timeout (300s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def add_dependency(self, project_dir: str, packages: list[str], manager: str = "npm", dev: bool = False) -> dict:
        try:
            if manager == "npm":
                flag = "--save-dev" if dev else ""
                cmd = f"npm install {flag} {' '.join(packages)}".strip()
            elif manager == "pip":
                cmd = f"pip install {' '.join(packages)}"
            elif manager == "yarn":
                flag = "--dev" if dev else ""
                cmd = f"yarn add {flag} {' '.join(packages)}".strip()
            else:
                return {"success": False, "error": f"Manager tidak didukung: {manager}"}

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            success = process.returncode == 0

            return {
                "success": success,
                "packages": packages,
                "output": stdout.decode("utf-8", errors="replace")[:2000],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def run_dev_server(self, project_dir: str, framework: str) -> dict:
        template = FRAMEWORK_TEMPLATES.get(framework)
        if not template:
            return {"success": False, "error": f"Framework tidak dikenal: {framework}"}

        dev_cmd = template.get("dev_command")
        if not dev_cmd:
            return {"success": False, "error": f"Tidak ada perintah dev untuk {framework}"}

        try:
            process = await asyncio.create_subprocess_shell(
                dev_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            return {
                "success": True,
                "pid": process.pid,
                "command": dev_cmd,
                "message": f"Dev server dimulai: {dev_cmd} (PID: {process.pid})",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def build_project(self, project_dir: str, framework: str) -> dict:
        template = FRAMEWORK_TEMPLATES.get(framework)
        if not template:
            return {"success": False, "error": f"Framework tidak dikenal: {framework}"}

        build_cmd = template.get("build_command")
        if not build_cmd:
            return {"success": True, "message": f"Framework {framework} tidak memerlukan build"}

        try:
            process = await asyncio.create_subprocess_shell(
                build_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            success = process.returncode == 0

            return {
                "success": success,
                "command": build_cmd,
                "output": stdout.decode("utf-8", errors="replace")[:3000],
                "errors": stderr.decode("utf-8", errors="replace")[:1000] if not success else None,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _generate_gitignore(self, framework: str) -> str:
        common = "node_modules/\n.env\n.env.local\n*.log\n.DS_Store\n__pycache__/\n*.pyc\n.venv/\n"
        extra = {
            "react": "build/\n.react-scripts/\n",
            "vue": "dist/\n.vite/\n",
            "flask": "*.pyc\ninstance/\n.webassets-cache\n",
            "express": "dist/\n",
            "nextjs": ".next/\nout/\n",
            "fastapi": "*.pyc\n.mypy_cache/\n",
        }
        return common + extra.get(framework, "")

    def list_frameworks(self) -> list[dict]:
        result = []
        for name, template in FRAMEWORK_TEMPLATES.items():
            result.append({
                "name": name,
                "manager": template.get("manager", "unknown"),
                "dev_command": template.get("dev_command"),
                "dependencies": template.get("dependencies", []),
            })
        return result

    def get_project_structure(self, project_dir: str) -> dict:
        structure = {"directories": [], "files": []}
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", ".next", ".venv")]
            rel_root = os.path.relpath(root, project_dir)
            for d in dirs:
                structure["directories"].append(os.path.join(rel_root, d))
            for f in files:
                structure["files"].append(os.path.join(rel_root, f))
        return structure
