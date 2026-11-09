# 双仓部署手册：Gitee 主仓 + GitHub 镜像

> 目标：日常在 Gitee 推代码（国内快），GitHub 只用来给 Render 拉取。
> 一次 `git push`，两个仓库同时更新。
> 当前状态：本地仓库已初始化，45 个文件、1 次提交（`16eb998`），还没配远程地址。

---

## 0. 先确认本地仓库是好的

在 `cxcy` 目录打开 PowerShell：

```powershell
git log --oneline
git status
```

期望看到：

```
16eb998 feat: 闲行智策 v0.1 可运行雏形
On branch main
nothing to commit, working tree clean
```

如果 `git` 命令不存在，先装 Git（git-scm.com），装完重开终端。

首次使用还要配一次身份（只需一次）：

```powershell
git config --global user.name "夏镇宽"
git config --global user.email "你的邮箱"
```

---

## 1. 在 Gitee 建空仓库

1. 打开 <https://gitee.com>，登录（没号就注册，需要手机号）。
2. 右上角 **+** → **新建仓库**。
3. 填写：
   - **仓库名称**：`xianxing-zhiche`（随意，建议英文）
   - **仓库路径**：自动生成，记住它，后面要用
   - **是否开源**：选 **公开**（如果以后要用 CloudBase 部署，必须公开）
   - **初始化仓库**：**三个勾都别勾**（不要 README、不要 .gitignore、不要开源许可证）
4. 点 **创建**。

创建后页面会给出地址，形如：

```
https://gitee.com/你的用户名/xianxing-zhiche.git
```

> 为什么不能勾初始化？因为勾了会生成一个初始提交，和你本地的提交"分叉"，
> 推送时会被拒绝（`Updates were rejected`）。空仓库最省事。

---

## 2. 在 GitHub 建空仓库

1. 打开 <https://github.com/new>。
2. **Repository name** 填 `xianxing-zhiche`（可以和 Gitee 不同名，但建议一致）。
3. 选 **Public**（私有也行，但 Render 拉私有仓库要额外授权 GitHub App）。
4. **Add a README / .gitignore / license 全都不勾**。
5. 点 **Create repository**。

拿到地址：

```
https://github.com/你的用户名/xianxing-zhiche.git
```

---

## 3. 配置"一个 remote、两个推送地址"

在 `cxcy` 目录执行（把两个地址换成你自己的）：

```powershell
# ① 设主地址（fetch 用 Gitee）
git remote add origin https://gitee.com/你的用户名/xianxing-zhiche.git

# ② 添加第一个推送地址（Gitee）
git remote set-url --add --push origin https://gitee.com/你的用户名/xianxing-zhiche.git

# ③ 添加第二个推送地址（GitHub）
git remote set-url --add --push origin https://github.com/你的用户名/xianxing-zhiche.git

# ④ 检查
git remote -v
```

期望输出：

```
origin  https://gitee.com/你的用户名/xianxing-zhiche.git (fetch)
origin  https://gitee.com/你的用户名/xianxing-zhiche.git (push)
origin  https://github.com/你的用户名/xianxing-zhiche.git (push)
```

**关键是两行 push**：git 会按顺序往两个地址各推一次。

> 这三条命令我在本机用两个本地裸仓库实测过：一次 `git push` 后两个仓库拿到的是同一个 commit。

---

## 4. 首次推送（会要求登录）

```powershell
git push -u origin main
```

### Gitee 认证

会弹窗要账号密码。**密码处填"私人令牌"，不是登录密码**：

1. Gitee → 右上角头像 → **设置** → 左侧 **私人令牌** → **生成新令牌**；
2. 描述随便写（如 `dev-push`），权限勾 **projects**（仓库读写）；
3. 复制生成的令牌，粘贴到弹窗的密码框；
4. 凭据管理器会记住，之后不用再输。

### GitHub 认证

- 如果装了 Git for Windows（自带 Credential Manager），会弹浏览器让你登录授权，点一下就好；
- 如果提示 `Support for password authentication was removed`，说明用了密码，改用 **Personal Access Token**：
  GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)** → Generate new token → 勾 `repo` → 复制，当作密码粘贴。

### 推送成功的标志

```
To https://gitee.com/你的用户名/xianxing-zhiche.git
 * [new branch]      main -> main
To https://github.com/你的用户名/xianxing-zhiche.git
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

两段 `new branch`，说明两边都收到了。

---

## 5. 验证

1. 打开两个仓库网页，应该能看到 `server/`、`web/`、`README.md` 等文件；
2. 本地再确认一次：

```powershell
git log --oneline -1
git remote -v
```

如果 GitHub 那边卡住/超时（国内常见），按这个顺序处理：

| 现象 | 处理 |
|---|---|
| `Failed to connect to github.com port 443` | 重试；或改用 SSH：`git remote set-url --add --push origin git@github.com:用户名/仓库.git` |
| 一直卡在 `Writing objects` | 项目小（<10MB），多半是网络抖动，`Ctrl+C` 后重试 |
| 部分推送失败 | `git push origin main` 会两处都推；只想推一个用 `git push https://gitee.com/... main` |

---

## 6. 日常流程（以后每天就这样）

```powershell
cd "C:\Users\xzk\Documents\deepseek-harness\default-workspace\cxcy"

git status                 # 看改了什么
git add -A                 # 全部暂存
git commit -m "feat: 补上兼职场景的解析关键词"
git push                   # 一条命令，两个仓库同时更新
```

只推 Gitee（比如 GitHub 暂时连不上）：

```powershell
git push https://gitee.com/你的用户名/xianxing-zhiche.git main
```

只推 GitHub（部署前补一刀）：

```powershell
git push https://github.com/你的用户名/xianxing-zhiche.git main
```

---

## 7. 可选：加一个开发分支

一个人开发可以只在 `main` 上推；多人协作建议：

```powershell
git branch dev
git switch dev
# 开发、提交...
git push -u origin dev     # 两边都会建 dev 分支
```

合并回主分支：

```powershell
git switch main
git merge dev
git push
```

---

## 8. 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| `Updates were rejected because the remote contains work...` | 建仓库时勾了 README，远程有初始提交 | `git pull --rebase origin main` 后再推；或删仓库重建（不勾初始化） |
| `fatal: not a git repository` | 不在 `cxcy` 目录 | `cd` 到有 `.git` 的目录 |
| 推送要求输入密码，输了登录密码却失败 | Gitee/GitHub 都不再用登录密码 | 用私人令牌 / PAT |
| `remote origin already exists` | 之前配过 | `git remote remove origin` 重来 |
| 提示文件太大 | 误提交了 `.venv` 或数据库 | 检查 `.gitignore`；已提交的用 `git rm --cached 文件名` 移除后重新提交 |
| 中文文件名显示成转义 | Git 默认转义 | `git config --global core.quotepath false` |
| 两个仓库内容不一致 | 只推了一边 | 看 `git remote -v` 的两个 push 地址，重新 `git push` |

---

## 9. 提交前的安全检查（很重要）

```powershell
git status
```

确认**没有**这些东西被提交：

- [ ] `.env`（含 API Key）
- [ ] `data/app.db`（演示数据）
- [ ] `.venv/`（几千个文件）
- [ ] 真实的合同/行程截图里带个人信息

`.gitignore` 已经排除了前三项，但**提交前扫一眼 `git status` 是最便宜的习惯**。

如果已经误提交了 Key：

1. 立刻去平台**吊销/重置**那个 Key（这步最重要，历史记录删了也没用）；
2. 再从仓库里移除文件并提交。

---

## 10. 和部署的关系

| 平台 | 用哪个仓库 |
|---|---|
| Render | **GitHub**（Render 只接 GitHub / GitLab / Bitbucket） |
| 腾讯云 CloudBase 云托管 | **Gitee 公开地址**（官方支持填公开 Git 仓库） |
| 本机 / 局域网 | 不需要远程仓库 |

也就是说：**双仓是为了"日常用 Gitee 快、部署两条路都能走"**，不是为了炫技。
