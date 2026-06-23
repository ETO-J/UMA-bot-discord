## Nginx 反向代理部署指南

### 1. 安装 Nginx

**Windows:**
从 https://nginx.org/en/download.html 下载，解压到 `C:\nginx`。

**Linux:**
```bash
apt install nginx       # Debian/Ubuntu
yum install nginx       # CentOS/RHEL
```

### 2. 部署配置文件

将以下两个文件放入 Nginx 配置目录：

| 文件 | Windows 路径 | Linux 路径 |
|------|-------------|------------|
| `bourbon-draw.cn.conf` | `C:\nginx\conf\conf.d\` | `/etc/nginx/conf.d/` |
| `bourbon-draw.cn.shared.conf` | `C:\nginx\conf\conf.d\` | `/etc/nginx/conf.d/` |

```powershell
# Windows
Copy-Item -LiteralPath "webapp\nginx\bourbon-draw.cn.conf" -Destination "C:\nginx\conf\conf.d\"
Copy-Item -LiteralPath "webapp\nginx\bourbon-draw.cn.shared.conf" -Destination "C:\nginx\conf\conf.d\"
```

### 3. 修改静态文件路径

编辑 `bourbon-draw.cn.shared.conf`，把 `C:/Users/Administrator/bpdiscord/webapp/static` 替换为实际路径。

### 4. 修改 FastAPI 启动端口

确保 FastAPI 监听在 `127.0.0.1:8000`（当前默认值，无需修改）。

### 5. 启动顺序

```powershell
# 1. 启动 Nginx
Start-Process -FilePath "C:\nginx\nginx.exe"

# 2. 启动 FastAPI
cd webapp
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### 6. 验证

```bash
# Nginx 是否在监听
curl -I http://127.0.0.1

# 通过 Nginx 访问 API
curl http://127.0.0.1/api/auth/me

# 模拟后端停机（停止 FastAPI 后）
curl http://127.0.0.1          # 应返回 down.html
curl -I http://127.0.0.1/api/auth/me  # HTTP 502 → down.html
```

### 7. SSL 证书（可选）

如果已有域名证书，取消 `bourbon-draw.cn.conf` 中 HTTPS server 块的注释，填入证书路径。

### 8. 与 Cloudflare Tunnel 共存

如果当前使用 `cloudflared.exe`：

```
cloudflared → Nginx(:80) → FastAPI(:8000)
```

只需将 cloudflared 的 upstream 从 `localhost:8000` 改为 `localhost:80`。

### 9. Nginx 重载配置（修改后无需重启）

```powershell
C:\nginx\nginx.exe -s reload
```

```bash
# Linux
nginx -s reload
```
