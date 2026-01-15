# 用戶識別機制分析：如何知道是同一個人？

## 核心問題 (Core Question)

**問題**: "請問你如何知道是同一個人傳送的？"

**答案**: 目前系統**並不真正知道**是否為同一個人。系統只是透過**瀏覽器 localStorage 儲存的 UUID** 來「假設」是同一個人。

---

## 目前的識別機制 (Current Identification Mechanism)

### 識別方式：瀏覽器指紋 (Browser Fingerprinting)

```
用戶身份 = localStorage 中的 UUID
         = 瀏覽器 + localStorage 資料
         ≠ 真實的人
```

**實際上識別的是**:
- ✅ 同一個瀏覽器
- ✅ 同一個瀏覽器設定檔（Profile）
- ✅ 未清除瀏覽器資料的情況

**實際上無法識別**:
- ❌ 真實的人（姓名、身份證、Email）
- ❌ 跨裝置的同一個人
- ❌ 跨瀏覽器的同一個人
- ❌ 清除資料後的同一個人

---

## 詳細分析：什麼是「同一個人」？

### 情境 1: 真實世界的「同一個人」

```
真實世界:
    張三 (同一個人)
        ↓
    使用多個裝置:
        - 公司電腦 (Chrome)
        - 家裡電腦 (Firefox)
        - 手機 (Safari)

目前系統看到的:
    - user_id_A (公司電腦 Chrome)
    - user_id_B (家裡電腦 Firefox)
    - user_id_C (手機 Safari)

系統結論: 這是「三個不同的人」❌
真實情況: 這是「同一個人」✅
```

**結論**: 系統**無法識別**跨裝置的同一個人

### 情境 2: 同一個瀏覽器的「同一個人」

```
真實世界:
    張三 在自己的電腦上使用 Chrome
        ↓
    第一次訪問: 生成 user_id_A
    第二次訪問: 使用 user_id_A (localStorage)
    第三次訪問: 使用 user_id_A (localStorage)

系統結論: 這是「同一個人」✅
真實情況: 這是「同一個人」✅
```

**結論**: 系統**可以識別**同一瀏覽器的連續訪問

### 情境 3: 不同人使用同一個瀏覽器

```
真實世界:
    張三 使用公司共用電腦的 Chrome
    李四 使用公司共用電腦的 Chrome
    王五 使用公司共用電腦的 Chrome
        ↓
    localStorage 中的 user_id_A 被所有人共用

系統結論: 這是「同一個人」❌
真實情況: 這是「三個不同的人」✅
```

**結論**: 系統**無法區分**使用同一瀏覽器的不同人

---

## 技術實現細節 (Technical Implementation)

### 步驟 1: 瀏覽器生成 UUID

**位置**: [static/js/docai-client.js:75-100](static/js/docai-client.js#L75-L100)

```javascript
getUserId() {
    // 從 localStorage 讀取
    let userId = localStorage.getItem('docai_user_id');

    if (!userId) {
        // 生成隨機 UUID
        userId = crypto.randomUUID();  // 例: "550e8400-e29b-41d4-a716-446655440000"

        // 儲存到 localStorage
        localStorage.setItem('docai_user_id', userId);
    }

    return userId;
}
```

**關鍵點**:
- UUID 是**隨機生成**的，不包含任何個人資訊
- 儲存在**瀏覽器本地**，不在伺服器
- 只要 localStorage 未被清除，UUID 就會一直存在

### 步驟 2: localStorage 持久化

**localStorage 特性**:

| 特性 | 說明 | 影響 |
|------|------|------|
| 域名隔離 | 每個網站有獨立的 localStorage | DocAI 的 UUID 不會被其他網站看到 |
| 瀏覽器隔離 | Chrome、Firefox、Safari 各有自己的 localStorage | 同一個人使用不同瀏覽器會有不同 UUID |
| 設定檔隔離 | Chrome Profile 1 和 Profile 2 有不同的 localStorage | 同一個人使用不同設定檔會有不同 UUID |
| 裝置隔離 | 每個裝置有獨立的 localStorage | 同一個人使用不同裝置會有不同 UUID |
| 持久化 | 除非手動清除，否則永久保留 | UUID 可以跨會話存在 |

### 步驟 3: HTTP 標頭傳遞

**位置**: [static/js/docai-client.js:115](static/js/docai-client.js#L115)

```javascript
fetch('/api/v1/upload', {
    method: 'POST',
    headers: {
        'X-User-ID': this.userId  // 傳遞 UUID 到後端
    },
    body: formData
});
```

**關鍵點**:
- UUID 透過 HTTP 標頭 `X-User-ID` 發送
- 後端**信任**前端傳遞的 UUID（無驗證）
- 任何人都可以偽造 UUID（如果知道別人的 UUID）

### 步驟 4: 後端儲存到資料庫

**位置**: [app/Providers/file_metadata_provider/client.py:163-175](app/Providers/file_metadata_provider/client.py#L163-L175)

```python
_user_id = str(user_id)  # 將前端傳來的 UUID 轉為字串

await conn.execute("""
    INSERT INTO file_metadata (
        file_id, filename, file_type, file_size,
        upload_time, user_id, ...
    ) VALUES (?, ?, ?, ?, ?, ?, ...)
""", (
    file_id, filename, file_type, file_size,
    datetime.now(timezone.utc).isoformat(),
    _user_id,  # 儲存前端傳來的 UUID
    ...
))
```

**關鍵點**:
- 後端**不生成** UUID，只是儲存前端傳來的 UUID
- 後端**不驗證** UUID 是否屬於某個真實用戶
- 後端**假設**具有相同 UUID 的請求來自同一個人

---

## 識別的可靠性分析 (Reliability Analysis)

### ✅ 可靠的情境 (Reliable Scenarios)

1. **單一用戶，單一裝置，單一瀏覽器**:
   ```
   張三在自己的電腦上用 Chrome 訪問 DocAI
   → 每次都使用相同的 UUID
   → 系統可以正確識別「這是同一個人」✅
   ```

2. **短期內的連續訪問**:
   ```
   用戶今天上傳檔案 A，明天上傳檔案 B
   → 只要未清除瀏覽器資料
   → 系統可以正確識別「這是同一個人」✅
   ```

### ❌ 不可靠的情境 (Unreliable Scenarios)

1. **跨裝置訪問**:
   ```
   張三在公司電腦上傳檔案 A (UUID_1)
   張三在家裡電腦上傳檔案 B (UUID_2)
   → 系統無法識別這是同一個人 ❌
   ```

2. **跨瀏覽器訪問**:
   ```
   張三用 Chrome 上傳檔案 A (UUID_1)
   張三用 Firefox 上傳檔案 B (UUID_2)
   → 系統無法識別這是同一個人 ❌
   ```

3. **清除瀏覽器資料**:
   ```
   張三上傳檔案 A (UUID_1)
   張三清除瀏覽器資料
   張三再次訪問 (生成 UUID_2)
   → 系統認為這是兩個不同的人 ❌
   ```

4. **共用裝置**:
   ```
   張三用公司共用電腦上傳檔案 A (UUID_1)
   李四用同一台電腦上傳檔案 B (UUID_1)
   → 系統認為這是同一個人 ❌
   ```

5. **無痕模式**:
   ```
   張三用無痕模式訪問 (生成 UUID_temp)
   關閉無痕視窗 (UUID_temp 消失)
   張三再次用無痕模式訪問 (生成新的 UUID_temp2)
   → 系統認為這是兩個不同的人 ❌
   ```

---

## 安全性問題 (Security Issues)

### ⚠️ 問題 1: UUID 可被偽造 (UUID Spoofing)

**攻擊場景**:
```javascript
// 攻擊者可以在瀏覽器 Console 執行
localStorage.setItem('docai_user_id', '別人的UUID');
location.reload();

// 現在攻擊者可以假裝成別人上傳檔案
```

**後果**:
- 攻擊者可以假裝成其他用戶
- 攻擊者可以存取其他用戶的檔案（如果實作了檔案列表功能）
- 無法追蹤真實的操作者

### ⚠️ 問題 2: 沒有身份驗證 (No Authentication)

**現況**:
```
前端說: "我的 user_id 是 550e8400-..."
後端說: "好的，我相信你" ✅ (無驗證)
```

**正常的身份驗證應該是**:
```
前端說: "我的帳號是 zhang3，密碼是 xxx"
後端說: "讓我驗證... 正確！這是你的 token"
前端說: "這是我的 token，請處理我的請求"
後端說: "token 有效，確認是 zhang3" ✅ (有驗證)
```

### ⚠️ 問題 3: 無法撤銷或鎖定用戶 (Cannot Revoke or Lock Users)

**現況**:
- 如果某個 UUID 被濫用，無法封鎖
- 因為用戶可以隨時生成新的 UUID（清除 localStorage）
- 沒有「封鎖用戶」或「停用帳號」的機制

---

## 真實的用戶識別方案 (Real User Identification Solutions)

### 方案 1: 基於帳號的認證系統 (Account-Based Authentication)

#### 實作方式

```sql
-- 建立真實的用戶表
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,              -- UUID (伺服器生成)
    email TEXT UNIQUE NOT NULL,            -- Email (用於登入)
    username TEXT UNIQUE NOT NULL,         -- 用戶名
    password_hash TEXT NOT NULL,           -- 密碼雜湊
    full_name TEXT,                        -- 真實姓名
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- 建立會話表
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,           -- Session ID
    user_id TEXT NOT NULL,                 -- 關聯到 users.user_id
    token TEXT UNIQUE NOT NULL,            -- JWT token
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

#### 工作流程

```
1. 用戶註冊:
   POST /api/v1/auth/register
   Body: { email, username, password, full_name }
   → 伺服器建立用戶記錄
   → 返回: { user_id, message: "註冊成功" }

2. 用戶登入:
   POST /api/v1/auth/login
   Body: { email, password }
   → 伺服器驗證密碼
   → 生成 JWT token
   → 返回: { token, user_id, username }

3. 上傳檔案:
   POST /api/v1/upload
   Headers: { Authorization: "Bearer <JWT_token>" }
   → 伺服器驗證 token
   → 從 token 解析出 user_id
   → 儲存檔案與 user_id 關聯

4. 查詢檔案:
   GET /api/v1/files
   Headers: { Authorization: "Bearer <JWT_token>" }
   → 伺服器驗證 token
   → 只返回該 user_id 的檔案
```

#### 優點

- ✅ 真正識別用戶（透過 Email/密碼）
- ✅ 跨裝置同步（登入後所有裝置共用帳號）
- ✅ 安全性高（密碼雜湊、JWT token）
- ✅ 可以撤銷會話（登出、強制登出）
- ✅ 可以封鎖用戶

### 方案 2: OAuth 第三方登入 (OAuth Third-Party Login)

#### 支援的提供者

- Google OAuth 2.0
- GitHub OAuth
- Microsoft Azure AD
- Facebook Login

#### 工作流程

```
1. 用戶點擊「使用 Google 登入」:
   → 重定向到 Google OAuth 頁面

2. 用戶在 Google 授權:
   → Google 返回授權碼

3. 後端交換 token:
   → 使用授權碼向 Google 請求 access_token
   → 使用 access_token 取得用戶資訊（email, name, picture）

4. 後端建立或更新用戶:
   → 檢查 email 是否已存在
   → 不存在: 建立新用戶
   → 存在: 更新最後登入時間

5. 返回 JWT token:
   → 前端儲存 token
   → 後續請求使用 token
```

#### 優點

- ✅ 無需管理密碼（安全性更高）
- ✅ 用戶體驗好（一鍵登入）
- ✅ 跨裝置同步
- ✅ 可以取得用戶真實資訊（Email、姓名、頭像）

### 方案 3: 混合方案（推薦）

**保留 UUID + 新增真實認證**

```sql
-- 擴展現有的 users 表
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,              -- UUID (帳號識別)
    email TEXT UNIQUE,                     -- Email (用於登入，可選)
    username TEXT UNIQUE,                  -- 用戶名 (可選)
    password_hash TEXT,                    -- 密碼雜湊 (可選)
    anonymous BOOLEAN DEFAULT TRUE,        -- 是否為匿名用戶
    device_uuid TEXT,                      -- 前端生成的 UUID (追蹤裝置)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- file_metadata 關聯到 users.user_id
ALTER TABLE file_metadata
ADD FOREIGN KEY (user_id) REFERENCES users(user_id);
```

**工作流程**:

```
情境 1: 匿名用戶 (Anonymous User)
    1. 前端生成 device_uuid
    2. 後端建立匿名用戶記錄: anonymous=TRUE
    3. 用戶可以上傳檔案，但只能在同一裝置存取

情境 2: 註冊用戶 (Registered User)
    1. 用戶選擇「註冊」或「登入」
    2. 後端建立真實用戶記錄: anonymous=FALSE
    3. 將現有的匿名檔案轉移到真實帳號
    4. 用戶可以跨裝置存取檔案

情境 3: 匿名轉正式 (Anonymous to Registered)
    1. 匿名用戶點擊「建立帳號」
    2. 提供 Email 和密碼
    3. 後端更新用戶記錄: anonymous=FALSE
    4. 保留原有的檔案關聯
```

**優點**:
- ✅ 無需註冊即可使用（降低使用門檻）
- ✅ 可以升級到真實帳號（跨裝置同步）
- ✅ 保留現有的檔案（不會遺失）
- ✅ 靈活性高（支援匿名和註冊用戶）

---

## 比較表 (Comparison Table)

| 特性 | 目前方案 (UUID) | 帳號認證 | OAuth | 混合方案 |
|------|----------------|----------|-------|----------|
| 識別真實用戶 | ❌ | ✅ | ✅ | ✅ |
| 跨裝置同步 | ❌ | ✅ | ✅ | ✅ (註冊後) |
| 無需註冊 | ✅ | ❌ | ❌ | ✅ |
| 安全性 | ⚠️ 低 | ✅ 高 | ✅ 高 | ✅ 中-高 |
| 可撤銷會話 | ❌ | ✅ | ✅ | ✅ |
| 可封鎖用戶 | ❌ | ✅ | ✅ | ✅ |
| 實作複雜度 | ✅ 簡單 | ⚠️ 中等 | ⚠️ 中等 | ⚠️ 複雜 |
| 維護成本 | ✅ 低 | ⚠️ 中等 | ⚠️ 中等 | ⚠️ 高 |

---

## 建議 (Recommendations)

### 短期建議 (Short-Term)

**如果只是原型或內部使用**:
- 目前的 UUID 方案**可以接受**
- 新增基本的使用者文件，說明限制
- 新增瀏覽器 Console 工具讓用戶檢查自己的 UUID

### 中期建議 (Mid-Term)

**如果準備對外開放或有少量用戶**:
- 實作**混合方案**（保留匿名 + 新增註冊）
- 優先支援 Email/密碼註冊
- 新增「匿名轉正式」功能
- 新增基本的會話管理

### 長期建議 (Long-Term)

**如果有大量用戶或商業化**:
- 實作完整的**帳號認證系統**
- 新增 **OAuth 第三方登入**（Google、GitHub）
- 實作**雙因素認證** (2FA)
- 新增**會話管理**和**裝置管理**
- 實作**權限管理**和**角色管理**
- 新增**審計日誌**（追蹤用戶操作）

---

## 實作範例 (Implementation Example)

### 快速實作：新增 UUID 顯示功能

**在前端新增用戶資訊顯示**:

```javascript
// 在頁面上顯示當前 user_id
function showUserInfo() {
    const userId = localStorage.getItem('docai_user_id');
    const infoDiv = document.createElement('div');
    infoDiv.style.cssText = 'position: fixed; top: 10px; right: 10px; background: #f0f0f0; padding: 10px; border-radius: 5px; font-size: 12px;';
    infoDiv.innerHTML = `
        <strong>User ID:</strong><br>
        <code>${userId}</code><br>
        <button onclick="copyUserId()">複製</button>
        <button onclick="clearUserId()">清除</button>
    `;
    document.body.appendChild(infoDiv);
}

function copyUserId() {
    const userId = localStorage.getItem('docai_user_id');
    navigator.clipboard.writeText(userId);
    alert('已複製 User ID');
}

function clearUserId() {
    if (confirm('確定要清除 User ID？這會導致無法存取之前上傳的檔案。')) {
        localStorage.removeItem('docai_user_id');
        location.reload();
    }
}

// 在 DOMContentLoaded 時呼叫
document.addEventListener('DOMContentLoaded', showUserInfo);
```

---

## 結論 (Conclusion)

### 回答原始問題

**問題**: "請問你如何知道是同一個人傳送的？"

**答案**:

目前系統**並不真正知道**是否為同一個人。系統只是透過以下假設來「猜測」:

1. **假設**: 具有相同 UUID 的請求來自同一個人
2. **實際**: UUID 儲存在瀏覽器 localStorage 中
3. **限制**:
   - ❌ 無法識別跨裝置的同一個人
   - ❌ 無法區分使用同一瀏覽器的不同人
   - ❌ 無法防止 UUID 被偽造
   - ❌ 無法驗證用戶的真實身份

### 真實識別用戶的唯一方法

**只有實作真正的用戶認證系統**（帳號/密碼、OAuth）**才能真正識別同一個人**。

目前的 UUID 方案只是一個**裝置/瀏覽器識別符**，不是**用戶識別符**。

---

**分析完成日期**: 2025-11-03
