# OpenClaw AWD 靶机镜像构建指南

## 快速开始

```bash
cd target-image/ctf
docker build -t openclaw/ctf-target:v1 .
docker run -d -p 3000:3000 -p 2222:22 -e SSH_PASSWORD=test123 openclaw/ctf-target:v1
```

## 镜像说明

本项目提供两种靶机镜像：

| 镜像 | Dockerfile | 用途 |
|------|-----------|------|
| `openclaw/ctf-target:v1` | `ctf/Dockerfile` | 生产环境，含完整 CTF 功能（supervisor、app.py、flag_sync.sh） |
| `openclaw/ctf-target:test` | `Dockerfile.test` | 开发/测试用轻量镜像，仅含基础 HTTP + SSH 功能 |

## 测试验证

### 1. HTTP 服务测试
```bash
curl -I http://localhost:3000
```
预期输出: `HTTP/1.1 200 OK`

### 2. SSH 登录测试
```bash
ssh -p 2222 defender@localhost
```
密码: `test123` (或环境变量 `SSH_PASSWORD` 设置的值)

### 3. 数据库写入测试
```bash
docker exec <container_id> sqlite3 /app/arena/arena.db "SELECT * FROM arena_secret;"
```
预期输出: 显示初始 Flag 记录

### 4. Flag 注入测试
```bash
docker exec <container_id> sqlite3 /app/arena/arena.db \
  "UPDATE arena_secret SET flag='FLAG{test_flag_12345}' WHERE id=1;"
  
docker exec <container_id> sqlite3 /app/arena/arena.db \
  "SELECT flag FROM arena_secret WHERE id=1;"
```
预期输出: `FLAG{test_flag_12345}`

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SSH_PASSWORD` | SSH 用户 defender 的密码 | `changeme` |
| `CTF_SEED` | 靶机内置凭据/数据库文件名的随机种子。裁判引擎默认以 match_id 注入，保证每场靶机细节不同且可按比赛复现；不设置时使用历史固定值 | 空（不随机化） |

## 文件结构

```
target-image/
├── ctf/
│   ├── Dockerfile              # 生产环境镜像
│   ├── app.py                  # CTF Web 应用
│   ├── entrypoint.sh           # 容器启动脚本
│   ├── flag_sync.sh            # Flag 同步脚本
│   └── supervisord.conf        # Supervisor 配置
├── Dockerfile.test             # 测试环境轻量镜像
├── init_arena_db.sql           # 数据库初始化脚本
├── docker-entrypoint.sh        # 生产环境启动脚本
├── docker-entrypoint-test.sh   # 测试环境启动脚本
├── test.sh                     # 自动化测试脚本
└── README.md                   # 本文件
```

## 数据库结构

### arena_secret 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| flag | TEXT | Flag 内容，唯一 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

## 端口映射

| 容器端口 | 服务 |
|----------|------|
| 3000 | CTF Web 服务 |
| 22 | SSH |

## 安全说明

- SSH 仅允许用户 `defender` 登录
- 默认密码应在生产环境中通过环境变量修改
- 数据库文件权限设置为 644，允许外部写入

## 故障排查

### SSH 无法连接
```bash
docker exec <container_id> service ssh status
docker logs <container_id>
```

### 数据库不存在
```bash
docker exec <container_id> ls -la /app/arena/
docker exec <container_id> cat /app/arena/init_arena_db.sql
```

### Web 服务无法访问
```bash
docker exec <container_id> curl http://localhost:3000
docker logs <container_id>
```

## 镜像说明

本项目提供两种靶机镜像：

| 镜像 | Dockerfile | 用途 |
|------|-----------|------|
| `openclaw/ctf-target:v1` | `ctf/Dockerfile` | 生产环境，含完整 CTF 功能（supervisor、app.py、flag_sync.sh） |
| `openclaw/ctf-target:test` | `Dockerfile.test` | 开发/测试用轻量镜像，仅含基础 HTTP + SSH 功能 |

## 测试验证

### 1. HTTP 服务测试
```bash
curl -I http://localhost:3000
```
预期输出: `HTTP/1.1 200 OK`

### 2. SSH 登录测试
```bash
ssh -p 2222 defender@localhost
```
密码: `test123` (或环境变量 `SSH_PASSWORD` 设置的值)

### 3. 数据库写入测试
```bash
docker exec <container_id> sqlite3 /app/arena/arena.db "SELECT * FROM arena_secret;"
```
预期输出: 显示初始 Flag 记录

### 4. Flag 注入测试
```bash
docker exec <container_id> sqlite3 /app/arena/arena.db \
  "UPDATE arena_secret SET flag='FLAG{test_flag_12345}' WHERE id=1;"
  
docker exec <container_id> sqlite3 /app/arena/arena.db \
  "SELECT flag FROM arena_secret WHERE id=1;"
```
预期输出: `FLAG{test_flag_12345}`

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SSH_PASSWORD` | SSH 用户 defender 的密码 | `changeme` |
| `CTF_SEED` | 靶机内置凭据/数据库文件名的随机种子。裁判引擎默认以 match_id 注入，保证每场靶机细节不同且可按比赛复现；不设置时使用历史固定值 | 空（不随机化） |

## 文件结构

```
target-image/
├── ctf/
│   ├── Dockerfile              # 生产环境镜像
│   ├── app.py                  # CTF Web 应用
│   ├── entrypoint.sh           # 容器启动脚本
│   ├── flag_sync.sh            # Flag 同步脚本
│   └── supervisord.conf        # Supervisor 配置
├── Dockerfile.test             # 测试环境轻量镜像
├── init_arena_db.sql           # 数据库初始化脚本
├── docker-entrypoint.sh        # 生产环境启动脚本
├── docker-entrypoint-test.sh   # 测试环境启动脚本
├── test.sh                     # 自动化测试脚本
└── README.md                   # 本文件
```

## 数据库结构

### arena_secret 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| flag | TEXT | Flag 内容，唯一 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

## 端口映射

| 容器端口 | 服务 |
|----------|------|
| 3000 | CTF Web 服务 |
| 22 | SSH |

## 安全说明

- SSH 仅允许用户 `defender` 登录
- 默认密码应在生产环境中通过环境变量修改
- 数据库文件权限设置为 644，允许外部写入

## 故障排查

### SSH 无法连接
```bash
docker exec <container_id> service ssh status
docker logs <container_id>
```

### 数据库不存在
```bash
docker exec <container_id> ls -la /app/arena/
docker exec <container_id> cat /app/arena/init_arena_db.sql
```

### Web 服务无法访问
```bash
docker exec <container_id> curl http://localhost:3000
docker logs <container_id>
```

## 镜像说明

本项目提供两种靶机镜像：

| 镜像 | Dockerfile | 用途 |
|------|-----------|------|
| `openclaw/ctf-target:v1` | `ctf/Dockerfile` | 生产环境，含完整 CTF 功能（supervisor、app.py、flag_sync.sh） |
| `openclaw/ctf-target:test` | `Dockerfile.test` | 开发/测试用轻量镜像，仅含基础 HTTP + SSH 功能 |

## 测试验证

### 1. HTTP 服务测试
```bash
curl -I http://localhost:3000
```
预期输出: `HTTP/1.1 200 OK`

### 2. SSH 登录测试
```bash
ssh -p 2222 defender@localhost
```
密码: `test123` (或环境变量 `SSH_PASSWORD` 设置的值)

### 3. 数据库写入测试
```bash
docker exec <container_id> sqlite3 /app/arena/arena.db "SELECT * FROM arena_secret;"
```
预期输出: 显示初始 Flag 记录

### 4. Flag 注入测试
```bash
docker exec <container_id> sqlite3 /app/arena/arena.db \
  "UPDATE arena_secret SET flag='FLAG{test_flag_12345}' WHERE id=1;"
  
docker exec <container_id> sqlite3 /app/arena/arena.db \
  "SELECT flag FROM arena_secret WHERE id=1;"
```
预期输出: `FLAG{test_flag_12345}`

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SSH_PASSWORD` | SSH 用户 defender 的密码 | `changeme` |
| `CTF_SEED` | 靶机内置凭据/数据库文件名的随机种子。裁判引擎默认以 match_id 注入，保证每场靶机细节不同且可按比赛复现；不设置时使用历史固定值 | 空（不随机化） |

## 文件结构

```
target-image/
├── ctf/
│   ├── Dockerfile              # 生产环境镜像
│   ├── app.py                  # CTF Web 应用
│   ├── entrypoint.sh           # 容器启动脚本
│   ├── flag_sync.sh            # Flag 同步脚本
│   └── supervisord.conf        # Supervisor 配置
├── Dockerfile.test             # 测试环境轻量镜像
├── init_arena_db.sql           # 数据库初始化脚本
├── docker-entrypoint.sh        # 生产环境启动脚本
├── docker-entrypoint-test.sh   # 测试环境启动脚本
├── test.sh                     # 自动化测试脚本
└── README.md                   # 本文件
```

## 数据库结构

### arena_secret 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| flag | TEXT | Flag 内容，唯一 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

## 端口映射

| 容器端口 | 服务 |
|----------|------|
| 3000 | CTF Web 服务 |
| 22 | SSH |

## 安全说明

- SSH 仅允许用户 `defender` 登录
- 默认密码应在生产环境中通过环境变量修改
- 数据库文件权限设置为 644，允许外部写入

## 故障排查

### SSH 无法连接
```bash
docker exec <container_id> service ssh status
docker logs <container_id>
```

### 数据库不存在
```bash
docker exec <container_id> ls -la /app/arena/
docker exec <container_id> cat /app/arena/init_arena_db.sql
```

### Web 服务无法访问
```bash
docker exec <container_id> curl http://localhost:3000
docker logs <container_id>
```
