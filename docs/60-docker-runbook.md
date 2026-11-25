# Docker 与首次接入操作手册（实施目标）

以下命令为**插件完成后的操作约定**，实施者须在 G0 后将占位符替换为实测路径与镜像信息。不要覆盖用户原有 Compose、CA 证书挂载、代理或数据目录。

## 1. 只读采集目标环境信息

```bash
docker ps --format 'table {{.Names}}	{{.Image}}	{{.Status}}'
docker inspect --format '{{.Image}}' CONTAINER_NAME
docker inspect --format '{{json .Mounts}}' CONTAINER_NAME
```

在 Runner 实际 Python 环境中核实 Host/SDK/Python 版本，并向用户输出脱敏路径映射表（共享 `host/`、Bot 插件目录、`ctx.paths.data_dir`、自定义 CA）。

## 2. 登录方式选择

### A. 浏览器与 CLI 同机

```bash
python scripts/login.py --data-dir ./private-runtime init-host
python scripts/login.py --data-dir ./private-runtime login
python scripts/login.py --data-dir ./private-runtime status
python scripts/login.py --data-dir ./private-runtime models
```

`--no-browser` 仅改为手动打开 URL，浏览器仍须能访问同一台机器的 `127.0.0.1` 回调端口。

### B. 浏览器在桌面，MaiBot 在 Docker/远端（官方自托管转移）

1. 在目标容器的真实 `ACTUAL_PLUGIN_DATA_DIR` 执行 `init-host` 生成独立 `host_identity.json`。
2. 在桌面电脑用同版本 CLI 完成 `login`。
3. 确认桌面端已停止所有使用/刷新该会话的进程后，直接复制桌面端 `data_dir/credentials.json` 经安全通道传至目标临时路径，并在 Unix 目标机执行 `chmod 600 PRIVATE_TRANSFER_FILE`。
4. 在容器内导入并检查：

```bash
python scripts/login.py --data-dir ACTUAL_PLUGIN_DATA_DIR init-host
python scripts/login.py --data-dir ACTUAL_PLUGIN_DATA_DIR import-credentials --from-file PRIVATE_TRANSFER_FILE
python scripts/login.py --data-dir ACTUAL_PLUGIN_DATA_DIR status
python scripts/login.py --data-dir ACTUAL_PLUGIN_DATA_DIR doctor --online
```

5. 确认成功后删除临时传输文件与桌面端副本；**不要在桌面端执行 `logout`**（否则会撤销已移交的同一 session）。

## 3. CLI 验证与手工配置 MaiBot

```bash
python scripts/login.py --data-dir ACTUAL_PLUGIN_DATA_DIR models
python scripts/login.py --data-dir ACTUAL_PLUGIN_DATA_DIR smoke --model ACTUAL_MODEL_SLUG --prompt '请只回复：订阅链路测试成功。'
python scripts/login.py --data-dir ACTUAL_PLUGIN_DATA_DIR config --model ACTUAL_MODEL_SLUG
```

备份原有 `host/model_catalog.toml` 后人工合并片段（不覆盖 `[inner].version`），在 Bot 配置中仅先绑定一个纯文本测试任务（不绑定依赖工具的 Planner 或视觉任务）。

## 4. 故障速查与回滚

- **回调失败**：确认浏览器与 CLI 同机、端口与 `127.0.0.1/auth/callback` 未被拦截。
- **CLI 已登录但插件显示未登录**：核对 `ctx.paths.data_dir`、容器内外挂载与 UID/GID。
- **429 / 暂停**：查看 [ChatGPT Usage](https://chatgpt.com/settings/usage)，确认后执行 `resume`。
- **SSL 失败**：保持原有代理与 CA 证书配置，严禁关闭 TLS 验证。
- **回滚**：先将测试任务切回原模型 → 禁用插件 → 按需执行 `logout`；恢复手工编辑前配置时仅撤销本次新增条目。
