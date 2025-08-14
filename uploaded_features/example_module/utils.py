def create_greeting(greeting, target):
    """
    创建问候语
    :param greeting: 问候语
    :param target: 目标
    :return: 完整的问候语
    """
    return f"{greeting}, {target}!"

def reverse_string(s):
    """
    反转字符串
    :param s: 输入字符串
    :return: 反转后的字符串
    """
    return s[::-1]

def count_words(s):
    """
    计算字符串中的单词数
    :param s: 输入字符串
    :return: 单词数
    """
    return len(s.split())