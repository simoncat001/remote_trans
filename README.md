# remote_trans

远程传输接口请求代码

## 监控上传命令速查
先在 `config/config.json` 填好登录账号、密码和模板 ID（`template_ids` 字段内按类型区分），脚本会默认读取该文件，不再从命令行传递凭据。使用 `program/metadata_transfer.py` 监听仪器数据目录、提取元数据并上传。如需自定义后端域名，可用 `--base-url` 覆盖；如果配置文件不在默认位置，可通过 `--config` 指定路径，或设置环境变量 `REMOTE_TRANS_CONFIG` 指向自定义的 JSON 文件。

配置文件示例：

```json
{
  "username": "<fill-your-username>",
  "password": "<fill-your-password>",
  "template_ids": {
    "tem": "40884413-9949-4590-88b3-735a63b6e8f7",
    "nanoindenter": "1bada3ae-630f-4924-a8c5-270aaf155d90",
    "xrf": "6b2b3020-2f09-47e5-9c1f-e8595ebd4423",
    "synchrotron": "969a567c-7e9b-47d9-8157-c4670a282234"
  }
}
```

- **透射电镜（TEM）**
  ```bash
  python program/metadata_transfer.py \
    --root /path/to/tem_datasets \
    --type tem \
    --env prod \
    --process-existing
  ```

- **扫描电镜（SEM）**
  ```bash
  python program/metadata_transfer.py \
    --root /path/to/sem_datasets \
    --type sem \
    --env prod \
    --process-existing
  ```

- **X 射线荧光（XRF）**
  ```bash
  python program/metadata_transfer.py \
    --root /path/to/xrf_datasets \
    --type xrf \
    --env prod \
    --process-existing
  ```
  - 元数据默认从数据目录中的 `.atlas` 文件解析，脚本会自动挑选首个 `.atlas` 作为主文件。

- **X 射线衍射（XRD）**
  ```bash
  python program/metadata_transfer.py \
    --root /path/to/xrd_datasets \
    --type xrd \
    --env prod \
    --process-existing
  ```

- **同步辐射光谱**
  ```bash
  python program/metadata_transfer.py \
    --root /path/to/synchrotron_datasets \
    --type synchrotron \
    --env prod \
    --process-existing
  ```
  - 默认模板：`templates/synchrotron_radiation/同步辐射白光X射线衍射表征元数据规范 -2025.json`，默认模板 ID `969a567c-7e9b-47d9-8157-c4670a282234`（可在 `config/config.json` 的 `template_ids.synchrotron` 覆盖）。

参数说明：
- `--root` 监听的一级子目录根路径；每个子目录代表一个待上传数据集。
- `--type` 仪器数据类型，限于 `tem`、`sem`、`xrf`、`xrd`、`synchrotron`。
- `--env` 选择后端环境预设（`dev`/`prod`/`local`），或改用 `--base-url` 指定域名。
- `--config` 指向包含 `username`/`password` 以及 `template_ids` 的 JSON 配置文件，默认 `config/config.json`。
- `--process-existing` 启动时先处理已存在的子目录；可按需移除。

## SEM `.bcf` 元数据一键提取

`parse_full_bcf.py` 会把原始 `data/SEM/1.bcf` 拆成 100 份，逐块剥离像素数据、合并得到 `1_metadata_only.bcf`，然后解析为 JSON：

```bash
python parse_full_bcf.py data/SEM/1.bcf --output data/SEM/metadata.json
```

- 步骤顺序：① 拆分到 `data/SEM/1_split_parts/` → ② 精简为 `data/SEM/1_processed_parts/` → ③ 合并生成 `data/SEM/1_metadata_only.bcf` → ④ 解析写入 `metadata.json`。
- 主要参数：
  - `--parts` 控制拆分份数，默认 100。
  - `--split-dir`、`--processed-dir`、`--metadata-only` 可重定向各阶段输出。
  - `--force`（或 `--force-split/--force-process/--force-merge`）可强制重跑对应阶段。
  - `--cleanup` 会在成功后删除本次新生成的拆分/精简/合并文件。
  - `--compact` 输出紧凑 JSON，`--no-summary` 跳过终端摘要。

脚本默认复用已存在的拆分结果与精简文件，只在显式 `--force` 时重新构建，避免反复处理大文件。
