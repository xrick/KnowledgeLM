// =============================================================================
// DocAI MongoDB Schema Initialization
// =============================================================================
//
// 使用方式:
//   mongosh --file init_docai_mongodb.js
//
// 或連接到特定主機:
//   mongosh mongodb://localhost:27017 --file init_docai_mongodb.js
//
// =============================================================================
// Database: docai
// Collection: chat_sessions
//
// Schema:
// {
//     "_id": ObjectId,
//     "session_id": str (unique),
//     "user_id": str (optional),
//     "file_ids": [str],
//     "created_at": datetime,
//     "updated_at": datetime,
//     "messages": [
//         {
//             "role": "user" | "assistant" | "system",
//             "content": str,
//             "timestamp": datetime,
//             "metadata": {}
//         }
//     ],
//     "metadata": {}
// }
// =============================================================================

print("╔═══════════════════════════════════════════════════════════════════╗");
print("║           DocAI MongoDB Schema Initialization                     ║");
print("╚═══════════════════════════════════════════════════════════════════╝");
print("");

// 切換到 docai 資料庫
use docai;
print("📂 Using database: docai");

// =============================================================================
// 1. 創建 chat_sessions 集合
// =============================================================================
print("\n🔧 Step 1: Creating chat_sessions collection...");

if (!db.getCollectionNames().includes("chat_sessions")) {
    db.createCollection("chat_sessions", {
        validator: {
            $jsonSchema: {
                bsonType: "object",
                required: ["session_id", "created_at", "updated_at", "messages"],
                properties: {
                    session_id: {
                        bsonType: "string",
                        description: "Unique session identifier - required"
                    },
                    user_id: {
                        bsonType: ["string", "null"],
                        description: "Optional user identifier"
                    },
                    file_ids: {
                        bsonType: "array",
                        items: { bsonType: "string" },
                        description: "Files associated with this session"
                    },
                    created_at: {
                        bsonType: "date",
                        description: "Session creation timestamp - required"
                    },
                    updated_at: {
                        bsonType: "date",
                        description: "Last update timestamp - required"
                    },
                    messages: {
                        bsonType: "array",
                        items: {
                            bsonType: "object",
                            required: ["role", "content", "timestamp"],
                            properties: {
                                role: {
                                    enum: ["user", "assistant", "system"],
                                    description: "Message role - required"
                                },
                                content: {
                                    bsonType: "string",
                                    description: "Message content - required"
                                },
                                timestamp: {
                                    bsonType: "date",
                                    description: "Message timestamp - required"
                                },
                                metadata: {
                                    bsonType: "object",
                                    description: "Optional message metadata"
                                }
                            }
                        },
                        description: "Array of chat messages - required"
                    },
                    metadata: {
                        bsonType: "object",
                        description: "Optional session-level metadata"
                    }
                }
            }
        },
        validationLevel: "moderate",
        validationAction: "warn"
    });
    print("   ✅ Created collection: chat_sessions");
} else {
    print("   ℹ️  Collection chat_sessions already exists");
}

// =============================================================================
// 2. 創建索引
// =============================================================================
print("\n🔧 Step 2: Creating indexes...");

// session_id 唯一索引 (主查詢)
db.chat_sessions.createIndex(
    { "session_id": 1 },
    { unique: true, name: "idx_session_id_unique" }
);
print("   ✅ Index: idx_session_id_unique (session_id, unique)");

// user_id 索引 (按用戶查詢)
db.chat_sessions.createIndex(
    { "user_id": 1 },
    { name: "idx_user_id" }
);
print("   ✅ Index: idx_user_id (user_id)");

// created_at 降序索引 (最新優先)
db.chat_sessions.createIndex(
    { "created_at": -1 },
    { name: "idx_created_at" }
);
print("   ✅ Index: idx_created_at (created_at DESC)");

// updated_at 降序索引 (最近更新優先)
db.chat_sessions.createIndex(
    { "updated_at": -1 },
    { name: "idx_updated_at" }
);
print("   ✅ Index: idx_updated_at (updated_at DESC)");

// file_ids 索引 (按文件查詢)
db.chat_sessions.createIndex(
    { "file_ids": 1 },
    { name: "idx_file_ids" }
);
print("   ✅ Index: idx_file_ids (file_ids)");

// 複合索引: user_id + updated_at (用戶最近對話)
db.chat_sessions.createIndex(
    { "user_id": 1, "updated_at": -1 },
    { name: "idx_user_recent" }
);
print("   ✅ Index: idx_user_recent (user_id + updated_at DESC)");

// =============================================================================
// 3. 插入初始化測試文檔
// =============================================================================
print("\n🔧 Step 3: Inserting initialization test document...");

var testDoc = {
    session_id: "docai_init_test",
    user_id: "system",
    file_ids: [],
    created_at: new Date(),
    updated_at: new Date(),
    messages: [
        {
            role: "system",
            content: "DocAI MongoDB schema initialized successfully",
            timestamp: new Date(),
            metadata: {
                init_script: true,
                version: "1.0"
            }
        }
    ],
    metadata: {
        init_version: "1.0",
        init_date: new Date().toISOString(),
        description: "Initialization test document - can be safely deleted"
    }
};

var existing = db.chat_sessions.findOne({ session_id: "docai_init_test" });
if (!existing) {
    db.chat_sessions.insertOne(testDoc);
    print("   ✅ Inserted test document (session_id: docai_init_test)");
} else {
    // 更新現有文檔
    db.chat_sessions.updateOne(
        { session_id: "docai_init_test" },
        {
            $set: {
                updated_at: new Date(),
                "metadata.last_reinit": new Date().toISOString()
            }
        }
    );
    print("   ℹ️  Test document already exists, updated timestamp");
}

// =============================================================================
// 4. 顯示集合資訊
// =============================================================================
print("\n" + "═".repeat(70));
print("📊 Collection Summary");
print("═".repeat(70));

print("\n📁 Database: docai");
print("📁 Collection: chat_sessions");

print("\n📋 Indexes:");
var indexes = db.chat_sessions.getIndexes();
indexes.forEach(function(idx) {
    var keyStr = JSON.stringify(idx.key);
    var uniqueStr = idx.unique ? " (unique)" : "";
    print("   • " + idx.name + ": " + keyStr + uniqueStr);
});

print("\n📊 Collection Stats:");
var stats = db.chat_sessions.stats();
print("   Documents: " + stats.count);
print("   Storage Size: " + (stats.storageSize / 1024).toFixed(2) + " KB");
print("   Index Size: " + (stats.totalIndexSize / 1024).toFixed(2) + " KB");

// =============================================================================
// 5. 驗證
// =============================================================================
print("\n" + "═".repeat(70));
print("✅ Validation");
print("═".repeat(70));

// 測試插入
var validationDoc = {
    session_id: "validation_test_" + new Date().getTime(),
    user_id: "validator",
    file_ids: ["test_file_1"],
    created_at: new Date(),
    updated_at: new Date(),
    messages: [
        {
            role: "user",
            content: "Test message",
            timestamp: new Date(),
            metadata: {}
        }
    ],
    metadata: { test: true }
};

try {
    var result = db.chat_sessions.insertOne(validationDoc);
    print("\n   ✅ Insert validation: PASSED");

    // 清理測試文檔
    db.chat_sessions.deleteOne({ _id: result.insertedId });
    print("   ✅ Delete validation: PASSED");
} catch (e) {
    print("\n   ❌ Validation failed: " + e.message);
}

// 測試查詢
try {
    var doc = db.chat_sessions.findOne({ session_id: "docai_init_test" });
    if (doc) {
        print("   ✅ Query validation: PASSED");
    }
} catch (e) {
    print("   ❌ Query validation failed: " + e.message);
}

// =============================================================================
// 完成
// =============================================================================
print("\n" + "═".repeat(70));
print("🎉 DocAI MongoDB initialization complete!");
print("═".repeat(70));
print("\n連接配置:");
print("   URI:        mongodb://localhost:27017");
print("   Database:   docai");
print("   Collection: chat_sessions");
print("\n環境變數 (.env):");
print("   MONGODB_URI=mongodb://localhost:27017");
print("   MONGODB_DATABASE=docai");
print("   MONGODB_CHAT_COLLECTION=chat_sessions");
print("");
