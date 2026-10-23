# 从零发布到 PyPI · 手把手

> 这份文档解决两件事：**怎么注册 PyPI**，以及**那个脚本到底在干什么**。
> 全程约 40 分钟，其中 30 分钟是等邮件和填表，实际动手只有 10 分钟。

## 当前进度（2026-10-23）

| 步骤 | 状态 | 说明 |
|---|---|---|
| 包名迁移（发布名/导入名/命令名） | ✅ 完成 | 97 个测试全绿 |
| 构建 + 元数据自检 | ✅ 完成 | 两个产物 `PASSED` |
| 发到 TestPyPI | ✅ **完成** | https://test.pypi.org/project/trustguard-ai/0.1.0/ |
| 从 TestPyPI 安装验证 | ✅ 完成 | `pip install -i https://test.pypi.org/simple/ trustguard-ai` → `tguard demo` 正常 |
| 发到正式 PyPI | ✅ **完成** | https://pypi.org/project/trustguard-ai/0.1.0/ （2026-10-23 09:05 UTC） |
| 从正式 PyPI 安装验证 | ✅ 完成 | `pip install trustguard-ai` → `tguard demo` 正常 |
| README 徽章 | ✅ 完成 | 中英文 README 均已挂 PyPI / Python / License / Tests 徽章 |
| 吊销已暴露的 token | ⬜ **待办** | 两个站的 `local-upload` 都要删 |

> ⚠️ **两个 token 都已在对话里明文出现过，属于已泄露。** 去 https://test.pypi.org/manage/account/token/ 和 https://pypi.org/manage/account/token/ 把它们删掉，需要时再建一个**限定到 `trustguard-ai` 单个项目**的。习惯要从一开始就养对。

---

## 零、先把三个名字分清（这是最容易懵的地方）

Python 包有**三个不同的名字**，它们可以不一样：

| 名字 | 是什么 | 你现在的是什么 | 在哪用 |
|---|---|---|---|
| **发布名** | 别人 `pip install` 后面写的东西 | `trustguard-ai` | `pip install trustguard-ai` |
| **导入名** | 代码里 `import` 后面写的东西 | `trustguard_ai` | `from trustguard_ai import TrustGuard` |
| **命令名** | 装完后在终端敲的东西 | `tguard` | `tguard demo` |

**为什么三个都不一样？** 因为原来的 `trustguard` 这个名字在 PyPI 上已经被人占了（而且做的是类似的事），连命令名也占了。所以：

- 发布名加了 `-ai` 后缀 → `trustguard-ai`
- 导入名用下划线 → `trustguard_ai`（Python 里不能用横杠）
- 命令名换成短的 → `tguard`（避免和对方冲突，也好敲）

这不是随便定的，是必须的。你已经改完了，不用再动。

---

## 一、PyPI 是什么

**PyPI = Python 的"应用商店"。** 你把包传上去，全世界任何人 `pip install` 就能装。

它有两个站，**账号是分开的**：

| 站点 | 网址 | 用途 |
|---|---|---|
| **TestPyPI** | https://test.pypi.org | 测试站。随便发、发错了可以重发，用来练手 |
| **PyPI** | https://pypi.org | 正式站。**发上去就删不掉了**（只能标记为废弃），所以第一次一定先在测试站练 |

**建议顺序：先在 TestPyPI 发一遍，成功了再发正式站。** 这就是脚本里 `-Test` 那个参数的意义。

---

## 二、第一步：注册账号（约 10 分钟）

### 1. 注册 TestPyPI（先练手）

1. 打开 https://test.pypi.org/account/register/
2. 填四项：
   - **Username**：建议 `jason218ljs`（和 GitHub 一致，方便别人认）
   - **Email**：用你的常用邮箱
   - **Password**：至少 12 位
   - **Confirm password**
3. 点 **Create account**
4. 去邮箱点验证链接（**可能在垃圾邮件里**，找不到就搜 "test.pypi"）
5. 验证后登录，它会**强制你开两步验证（2FA）**：
   - 手机装一个验证器 App（Microsoft Authenticator / Google Authenticator / 1Password 都行）
   - 扫它给的二维码
   - 输入 6 位动态码确认

> ⚠️ **2FA 是强制的，跳不过。** 而且那个恢复码（recovery codes）一定要存下来——手机丢了没它你就进不去账号。

### 2. 注册正式 PyPI

步骤完全一样，网址换成 https://pypi.org/account/register/

**用户名建议和 TestPyPI 保持一致**，省得记混。

---

## 三、第二步：创建 API token（约 3 分钟）

**为什么不用密码？** 因为 PyPI 不允许用密码上传（也不该用）。上传要用 token，而且 token 可以随时吊销，比密码安全。

### 在 TestPyPI 上建 token

1. 登录后点右上角头像 → **Account settings**
2. 左侧菜单找 **API tokens**（直接访问：https://test.pypi.org/manage/account/token/）
3. 点 **Add API token**
4. 填两个字段：
   - **Token name**：写 `local-upload`（随便，自己能看懂就行）
   - **Scope**：选 **Entire account (all projects)**
     > 第一次必须选这个，因为项目还没建出来，没法限定到具体项目。等发布成功后，建议回来改成只限 `trustguard-ai` 一个项目，更安全。
5. 点 **Add token**
6. **立刻复制那串 token**——它只显示一次，关掉就再也看不到了

token 长这样：

```
pypi-AgENdGVzdC5weXBpLm9yZwJIZXlK...
```

> 以 `pypi-` 开头，很长。**这就是密码**，不要发到任何聊天窗口、不要提交到 git。

### 在正式 PyPI 上再建一个

同样操作，网址换成 https://pypi.org/manage/account/token/

两个站的 token **不通用**，必须各建一个。

---

## 四、第三步：把 token 写进配置文件（约 2 分钟）

脚本需要知道去哪找 token。标准做法是放在用户目录下的 `.pypirc` 文件里。

### 操作

1. 按 `Win + R`，输入 `%USERPROFILE%`，回车——会打开你的用户文件夹（一般是 `C:\Users\18976`）
2. 在这个文件夹里**新建一个文本文件**，命名为 `.pypirc`
   > 注意前面有个点。Windows 可能不让你建以点开头的文件名——那就先建成 `pypirc.txt`，再用记事本「另存为」改成 `.pypirc`
3. 用记事本打开，粘贴下面内容，把两处 `pypi-xxx` 换成你刚才复制的两个 token：

```ini
[distutils]
index-servers =
    pypi
    testpypi

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-这里换成TestPyPI的token

[pypi]
username = __token__
password = pypi-这里换成正式PyPI的token
```

4. 保存

**几个容易错的地方：**

| 错误 | 后果 |
|---|---|
| `username` 写成你的用户名 | 失败。**必须写 `__token__`**（两个下划线，前后各两个） |
| token 复制时少了 `pypi-` 前缀 | 失败，认证不通过 |
| 两个 token 写反了 | TestPyPI 那个位置写了正式站的，会 403 |
| 文件名是 `pypirc.txt` 不是 `.pypirc` | 脚本找不到，提示要你输密码 |

---

## 五、第四步：先自检，不上传

现在回到 trustguard 目录，打开 PowerShell（在文件夹空白处右键 → "在终端中打开"），敲：

```powershell
.\publish_to_pypi.ps1 -CheckOnly
```

### 这个参数在干什么

**`-CheckOnly` = 只打包 + 自检，不发到网上。**

它做了四件事：

1. 找到 Python
2. 安装打包工具（`build` 和 `twine`）
3. **打包**：把你的代码压成两个文件放进 `dist/` 文件夹
   - `trustguard_ai-0.1.0.tar.gz` —— 源码包
   - `trustguard_ai-0.1.0-py3-none-any.whl` —— 安装包
4. **自检**：`twine check` 检查这两个包的元数据（README 能不能正常显示、必填字段有没有缺）

### 你会看到什么

```
[1/5] Python: C:\Users\18976\...\python.exe
      version 3.13.12
[2/5] 安装构建工具 build / twine ...
[3/5] 清理 dist/ build/ ...
[4/5] 构建 sdist + wheel ...
Successfully built trustguard_ai-0.1.0.tar.gz and trustguard_ai-0.1.0-py3-none-any.whl
      twine check ...
Checking dist/trustguard_ai-0.1.0-py3-none-any.whl: PASSED
Checking dist/trustguard_ai-0.1.0.tar.gz: PASSED
      版本：0.1.0

✅ 构建与自检通过。产物在 dist\ 下，未上传。
```

看到两个 **PASSED** 就说明包是健康的。**这一步不碰网络、不碰账号，纯本地操作**，随便跑多少次都行。

> 我已经替你跑过一遍了，两个都是 PASSED。

---

## 六、第五步：发到测试站练手（✅ 已完成，留作参考）

```powershell
.\publish_to_pypi.ps1 -Test
```

**`-Test` = 发到 TestPyPI（测试站），不是正式站。**

前面四步和 `-CheckOnly` 完全一样，只是最后多了一步上传。

成功后你会看到：

```
✅ 已上传到 TestPyPI。验证安装：
   pip install -i https://test.pypi.org/simple/ trustguard-ai
```

### 验证一下真的能装

复制上面那行命令，在一个新的终端里跑：

```powershell
pip install -i https://test.pypi.org/simple/ trustguard-ai
tguard demo
```

如果 `tguard demo` 能打印出那份可信性报告——**恭喜，你已经是一个 PyPI 包的作者了。**

> ⚠️ 测试站上装的时候可能会因为依赖问题报错，因为它不会去正式站找依赖。你这个项目零依赖，所以基本不会遇到。真遇到了截图给我。

### 实测结果（2026-10-23）

```
Uploading trustguard_ai-0.1.0-py3-none-any.whl  → 100%
Uploading trustguard_ai-0.1.0.tar.gz           → 100%
View at: https://test.pypi.org/project/trustguard-ai/0.1.0/

pip install -i https://test.pypi.org/simple/ trustguard-ai
  → Successfully installed trustguard-ai-0.1.0

tguard demo
  → [trustguard] verdict=warn mode=rule errors=0 warnings=1
```

包页面上的元数据也验证过了：摘要、作者、4 个 project_urls、关键词、11,322 字符的 README 正文全部正常渲染。

---

## 七、第六步：发正式站

确认测试站没问题之后：

```powershell
.\publish_to_pypi.ps1
```

**不带任何参数 = 发到正式 PyPI。**

成功后：

```powershell
pip install trustguard-ai
tguard demo
```

以及打开 https://pypi.org/project/trustguard-ai/ 就能看到你的页面了。

---

## 八、三个参数速查

| 命令 | 干什么 | 碰网络吗 | 什么时候用 |
|---|---|---|---|
| `.\publish_to_pypi.ps1 -CheckOnly` | 打包 + 自检 | 只装工具时联网 | 每次发布前，确认包没问题 |
| `.\publish_to_pypi.ps1 -Test` | 打包 + 自检 + 发测试站 | 是 | 第一次发布，练手 |
| `.\publish_to_pypi.ps1` | 打包 + 自检 + 发正式站 | 是 | 确认无误后正式发布 |

---

## 九、常见报错对照表

| 报错关键词 | 原因 | 怎么办 |
|---|---|---|
| `403 Forbidden` / `Invalid or non-existent authentication` | token 错、或 username 没写 `__token__` | 检查 `.pypirc`，重新复制 token |
| `File already exists` | 这个版本号已经发过了 | **PyPI 不允许覆盖**，改 `pyproject.toml` 里的 `version`（如 0.1.1）再发 |
| `The user 'xxx' isn't allowed to upload to project` | token 的 scope 限定了别的项目 | 重新建一个 Entire account 范围的 token |
| `No module named build` | 工具没装上 | 脚本会自动装；手动跑 `pip install build twine` |
| `twine check` 报 README 相关错误 | README 里有 PyPI 不支持的语法 | 把报错发我 |
| 找不到 `.pypirc` | 文件名不对 / 不在用户目录 | 确认路径是 `C:\Users\18976\.pypirc`，且没有 `.txt` 后缀 |
| PowerShell 提示「无法加载文件，因为在此系统上禁止运行脚本」 | 执行策略限制 | 跑一次 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，输 `Y` |

---

## 十、发完之后做什么

1. **立刻吊销已暴露的 token**：https://test.pypi.org/manage/account/token/ → 删掉 `local-upload`。正式站发布完成后，同样把正式站的 token 删掉重建一个只限 `trustguard-ai` 项目的
2. **开 GitHub Pages**：仓库 → Settings → Pages → Source 选 `Deploy from a branch` → 分支 `main`、目录 `/docs` → Save。几分钟后访问 `https://jason218-ljs.github.io/trustguard/`
3. **给 README 加徽章**（可选，但显得专业）：
   ```markdown
   [![PyPI](https://img.shields.io/pypi/v/trustguard-ai.svg)](https://pypi.org/project/trustguard-ai/)
   [![Python](https://img.shields.io/pypi/pyversions/trustguard-ai.svg)](https://pypi.org/project/trustguard-ai/)
   ```
4. **把 PyPI 链接补进简历和网站**——从今天起你的作品有了一个"官方地址"

---

## 附：为什么这些事值得做

发布一个 PyPI 包，技术上只值 10 分钟。但它改变的是**别人对你的默认假设**：

- 之前：「一个学生做了个课程项目」
- 之后：「`trustguard-ai` 的作者」

这个差别不在代码里，在对方点开链接的那 10 秒里。而你需要的那 10 秒，未来每一次谈客户、投实习、写文章都会用到。
