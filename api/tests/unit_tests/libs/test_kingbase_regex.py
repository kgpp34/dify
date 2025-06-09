import re


def test_kingbase_version_parsing():
    """测试 Kingbase 版本字符串解析"""

    # 测试用例：实际的 Kingbase 版本字符串
    test_cases = [
        {
            "version_string": "KingbaseES V008R006C007B0024PSC001 on x86_64-pc-linux-gnu",
            "expected": (8, 6, 7),
            "description": "完整的 Kingbase 版本字符串",
        },
        {
            "version_string": "KingbaseES V008R006C007B0024PSC001",
            "expected": (8, 6, 7),
            "description": "简化的 Kingbase 版本字符串",
        },
        {
            "version_string": "Kingbase V010R003C002B0001PSC001",
            "expected": (10, 3, 2),
            "description": "另一个 Kingbase 版本格式",
        },
        {
            "version_string": "PostgreSQL 14.2 on x86_64-pc-linux-gnu",
            "expected": (14, 2),
            "description": "PostgreSQL 版本字符串（应该走 fallback 逻辑）",
        },
    ]

    def parse_version(version_string):
        """解析版本字符串的函数"""
        # 首先尝试匹配 Kingbase - 修正后的正则表达式
        m = re.match(
            r".*(?:Kingbase|KingbaseES)\s*"
            r"V(\d{3})R(\d{3})C(\d{3})",  # 匹配 V008R006C007 格式
            version_string,
        )

        if m:
            # 将 Kingbase 版本号转换为 PostgreSQL 兼容格式
            # V008R006C007 -> (8, 6, 7)
            major = int(m.group(1))
            minor = int(m.group(2))
            patch = int(m.group(3))
            return (major, minor, patch)

        # 如果不是 Kingbase，尝试匹配 PostgreSQL
        m = re.match(
            r".*(?:PostgreSQL|EnterpriseDB) "
            r"(\d+)\.?(\d+)?(?:\.(\d+))?(?:\.\d+)?(?:devel|beta)?",
            version_string,
        )

        if not m:
            raise AssertionError(f"Could not determine version from string '{version_string}'")

        return tuple([int(x) for x in m.group(1, 2, 3) if x is not None])

    # 运行测试
    print("=== Kingbase 版本解析测试 ===")
    all_passed = True

    for i, test_case in enumerate(test_cases, 1):
        try:
            result = parse_version(test_case["version_string"])
            expected = test_case["expected"]

            if result == expected:
                print(f"✅ 测试 {i}: {test_case['description']}")
                print(f"   输入: {test_case['version_string']}")
                print(f"   结果: {result}")
                print()
            else:
                print(f"❌ 测试 {i}: {test_case['description']}")
                print(f"   输入: {test_case['version_string']}")
                print(f"   期望: {expected}")
                print(f"   实际: {result}")
                print()
                all_passed = False

        except Exception as e:
            print(f"❌ 测试 {i}: {test_case['description']}")
            print(f"   输入: {test_case['version_string']}")
            print(f"   错误: {e}")
            print()
            all_passed = False

    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试失败，需要调整正则表达式")

    return all_passed


if __name__ == "__main__":
    test_kingbase_version_parsing()
