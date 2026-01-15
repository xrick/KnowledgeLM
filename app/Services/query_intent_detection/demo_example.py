"""
Demo Example for Query Intent Detection Module

This file demonstrates how to use the new intent detection system
for presentation or testing purposes.
"""

from app.Services.query_intent_detection import IntentDetectorFactory
from app.Services.query_intent_detection.integration import (
    detect_multi_file_intent,
    detect_multi_file_intent_detailed,
    get_current_strategy_info
)


def demo_basic_usage():
    """Demo 1: 基本使用（向後相容）"""
    print("=" * 70)
    print("Demo 1: 基本使用（向後相容）")
    print("=" * 70)

    test_cases = [
        ("比較三份文件", 3),
        ("解釋這個文件", 1),
        ("產生四個來源文件的內容", 4),
        ("所有文件的資料", 5),
    ]

    for query, file_count in test_cases:
        is_multi = detect_multi_file_intent(query, file_count)
        print(f"Query: '{query}' (files={file_count})")
        print(f"  → Multi-file: {is_multi}")
        print()


def demo_detailed_results():
    """Demo 2: 獲取詳細偵測結果"""
    print("=" * 70)
    print("Demo 2: 獲取詳細偵測結果")
    print("=" * 70)

    test_cases = [
        ("比較三份文件", 3),           # Layer 1: 高信心關鍵字
        ("產生四份文件的摘要", 4),      # Layer 2: 數量模式
        ("所有文件的內容", 5),         # Layer 3: 範圍詞 + 內容詞
        ("給我10個檔案的資料", 10),    # Layer 2: 阿拉伯數字
    ]

    for query, file_count in test_cases:
        result = detect_multi_file_intent_detailed(query, file_count)
        print(f"Query: '{query}'")
        print(f"  → Is Multi-file: {result['is_multi_file']}")
        print(f"  → Confidence: {result['confidence']:.2f}")
        print(f"  → Detection Layer: {result['detection_layer']}")
        print(f"  → Matched Patterns: {result['matched_patterns']}")
        print()


def demo_factory_usage():
    """Demo 3: 使用工廠創建策略"""
    print("=" * 70)
    print("Demo 3: 使用工廠創建策略")
    print("=" * 70)

    # 創建 Regex 策略
    detector = IntentDetectorFactory.create_detector('regex')
    print(f"Created detector: {detector.name}")
    print()

    # 測試查詢
    test_cases = [
        ("三篇文章的差異", 3),
        ("七本書的比較", 7),
        ("給我2個檔案", 2),
        ("100份文件的摘要", 100),
    ]

    for query, file_count in test_cases:
        result = detector.detect_multi_file_intent(query, file_count)
        print(f"Query: '{query}'")
        print(f"  → {result}")
        print()


def demo_pattern_coverage():
    """Demo 4: 展示模式覆蓋範圍"""
    print("=" * 70)
    print("Demo 4: 展示模式覆蓋範圍")
    print("=" * 70)

    # 創建策略
    detector = IntentDetectorFactory.create_detector('regex')

    # 不同類型的查詢
    test_cases = [
        # Layer 1: 高信心關鍵字
        ("比較", 2),
        ("對比這些文件", 3),
        ("各別說明", 4),

        # Layer 2: 數量模式
        ("三份", 3),
        ("10個", 10),
        ("七篇文章", 7),

        # Layer 3: 範圍 + 內容
        ("所有的內容", 5),
        ("這些資料", 3),

        # Layer 4: 多文件暗示
        ("多份文件", 4),

        # 不應觸發
        ("這是單一文件", 5),
    ]

    layer_counts = {}

    for query, file_count in test_cases:
        result = detector.detect_multi_file_intent(query, file_count)

        # 統計每層的觸發次數
        if result.is_multi_file:
            layer = result.detection_layer
            layer_counts[layer] = layer_counts.get(layer, 0) + 1

        status = "✅" if result.is_multi_file else "❌"
        print(f"{status} '{query}' → {result.detection_layer} (confidence: {result.confidence:.2f})")

    print()
    print("Layer Trigger Statistics:")
    for layer, count in sorted(layer_counts.items()):
        print(f"  {layer}: {count} times")


def demo_strategy_info():
    """Demo 5: 查詢策略資訊"""
    print("=" * 70)
    print("Demo 5: 查詢策略資訊")
    print("=" * 70)

    # 獲取當前策略資訊
    info = get_current_strategy_info()

    print("Current Strategy Information:")
    print(f"  Strategy Type: {info['strategy_type']}")
    print(f"  Strategy Name: {info['strategy_name']}")
    print()

    print("Available Strategies:")
    for name, status in info['available_strategies'].items():
        icon = "✅" if status == "available" else "🔮"
        print(f"  {icon} {name}: {status}")
    print()

    # 獲取模式資訊
    from app.Services.query_intent_detection import RegexPatternStrategy
    detector = RegexPatternStrategy()
    pattern_info = detector.get_pattern_info()

    print("RegexPattern Configuration:")
    for layer in pattern_info['layers']:
        print(f"  Layer: {layer['name']}")
        print(f"    Type: {layer['type']}")
        print(f"    Confidence: {layer['confidence']}")
        if 'keywords' in layer:
            print(f"    Keywords: {layer['keywords'][:3]}... ({len(layer['keywords'])} total)")
        if 'patterns' in layer:
            print(f"    Patterns: {layer['patterns']}")
        print()


def run_all_demos():
    """執行所有 demo"""
    demos = [
        demo_basic_usage,
        demo_detailed_results,
        demo_factory_usage,
        demo_pattern_coverage,
        demo_strategy_info,
    ]

    for demo in demos:
        demo()
        input("按 Enter 繼續下一個 demo...")
        print("\n" * 2)


if __name__ == "__main__":
    print("\n")
    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║     Query Intent Detection Module - Demo Examples                ║")
    print("║     Strategy Pattern + Factory Method Implementation             ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")
    print("\n")

    # 執行所有 demo
    run_all_demos()

    print("=" * 70)
    print("Demo 完成！")
    print("=" * 70)
