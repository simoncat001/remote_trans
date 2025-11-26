# remote_trans

远程传输接口请求代码

## 监控上传命令速查
先在 `program/config.json` 填好登录账号和密码（字段 `username` / `password`），脚本会默认读取该文件，不再从命令行传递凭据。使用 `program/metadata_transfer.py` 监听仪器数据目录、提取元数据并上传。如需自定义后端域名，可用 `--base-url` 覆盖；如果配置文件不在默认位置，可通过 `--config` 指定路径。

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

参数说明：
- `--root` 监听的一级子目录根路径；每个子目录代表一个待上传数据集。
- `--type` 仪器数据类型，限于 `tem`、`sem`、`xrf`、`xrd`、`synchrotron`。
- `--env` 选择后端环境预设（`dev`/`prod`/`local`），或改用 `--base-url` 指定域名。
- `--config` 指向包含 `username`/`password` 的 JSON 配置文件，默认 `program/config.json`。
- `--process-existing` 启动时先处理已存在的子目录；可按需移除。
