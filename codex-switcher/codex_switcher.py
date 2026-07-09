import os
import sys
import json
import shutil
import argparse
from pathlib import Path

# 固定路径配置 (跨平台自适应：Windows下是 C:\Users\xxx\.codex，Linux下是 /home/xxx/.codex)
CODEX_DIR = Path.home() / ".codex"
PROFILES_DIR = Path.home() / ".codex_profiles"
STATE_FILE = PROFILES_DIR / "state.json"

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"current_profile": None}
    return {"current_profile": None}

def save_state(state):
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

def backup_current(profile_name, prompt_overwrite=False):
    """把当前 ~/.codex 的内容静默备份到指定 profile 文件夹"""
    if not CODEX_DIR.exists():
        return True # 没有任何记录，不需要备份
        
    profile_path = PROFILES_DIR / profile_name
    if profile_path.exists():
        if prompt_overwrite:
            ans = input(f"⚠️ 存档 '{profile_name}' 已存在。是否覆盖它？(y/n): ").strip().lower()
            if ans != 'y':
                print("操作已取消。")
                return False
        
        try:
            # 删除旧存档，如果被占用会抛出异常
            shutil.rmtree(profile_path)
        except Exception as e:
            print(f"\n❌ [覆盖失败] 无法删除已存在的存档 '{profile_name}'。")
            print("原因：该存档内的部分文件可能正被其他程序占用，或者您权限不足。")
            print(f"详情: {e}")
            return False
    
    try:
        # 忽略某些可能导致锁定的无用临时文件，进一步降低报错率
        ignore_patterns = shutil.ignore_patterns('*.sock', '*.lock')
        shutil.copytree(CODEX_DIR, profile_path, ignore=ignore_patterns)
        return True
    except shutil.Error as e:
        error_msg = str(e)
        if "WinError 33" in error_msg or "WinError 32" in error_msg or "locked" in error_msg.lower():
            print("\n❌ [文件占用错误] 操作已中止！")
            print("原因：您的 Codex 程序目前仍在后台运行，系统锁定了相关的数据库文件。")
            print("解决办法：请完全关闭所有的 Codex 命令行窗口或后台服务，然后再尝试切换/保存。")
            # 清理创建了一半的不完整存档
            if profile_path.exists():
                shutil.rmtree(profile_path, ignore_errors=True)
            return False
        else:
            print(f"\n❌ [未知复制错误] {e}")
            return False
    except Exception as e:
        print(f"\n❌ [未知错误] {e}")
        return False

def cmd_save(profile_name):
    """手动保存当前环境"""
    if not CODEX_DIR.exists():
        print(f"❌ 错误：找不到 {CODEX_DIR}，目前没有任何 codex 配置。")
        return
        
    print(f"正在保存当前状态至账号 '{profile_name}'...")
    if backup_current(profile_name, prompt_overwrite=True):
        state = load_state()
        state["current_profile"] = profile_name
        save_state(state)
        print(f"✅ 账号 '{profile_name}' 保存成功！")

def cmd_switch(profile_name):
    """切换账号"""
    state = load_state()
    current_profile = state.get("current_profile")
    
    # 1. 自动备份当前账号
    if current_profile:
        print(f"自动保存当前账号 '{current_profile}' 的状态...")
        if not backup_current(current_profile):
            return # 如果备份失败（比如文件被占），中止切换，保护数据
    elif CODEX_DIR.exists():
        # 用户没有指定过名字，但在切走前强行帮他保存到一个临时目录，以防丢数据
        print("发现未命名的现存状态，已自动备份至 'default_backup'...")
        if not backup_current("default_backup"):
            return
        
    # 2. 清空当前工作目录
    if CODEX_DIR.exists():
        try:
            shutil.rmtree(CODEX_DIR)
        except Exception as e:
            print(f"\n❌ [清理失败] 无法清空当前的 {CODEX_DIR}，可能有文件被占用。\n{e}")
            return
        
    # 3. 加载目标账号
    profile_path = PROFILES_DIR / profile_name
    print(f"正在加载账号 '{profile_name}' 的状态...")
    if profile_path.exists():
        try:
            shutil.copytree(profile_path, CODEX_DIR)
            print(f"✅ 成功切换至历史账号: {profile_name}")
        except Exception as e:
            print(f"\n❌ [加载失败] 无法将备份恢复至工作目录。\n{e}")
            return
    else:
        # 如果是全新的账号，创建一个空的文件夹，让 codex 重新生成
        CODEX_DIR.mkdir(parents=True, exist_ok=True)
        print(f"✨ 这是一个新账号，已为您创建全新的隔离环境: {profile_name}")
        
    # 4. 更新状态
    state["current_profile"] = profile_name
    save_state(state)

def cmd_list():
    """列出所有账号"""
    state = load_state()
    current = state.get("current_profile")
    
    if not PROFILES_DIR.exists():
        print("没有任何保存的账号。")
        return
        
    profiles = [d.name for d in PROFILES_DIR.iterdir() if d.is_dir()]
    
    print("=== OpenAI Codex 账号列表 ===")
    if not profiles:
        print("  (空)")
    for p in sorted(profiles):
        mark = "  <-- 当前激活" if p == current else ""
        print(f" - {p}{mark}")

def interactive_menu():
    while True:
        print("\n=== OpenAI Codex 多账号无缝切换工具 ===")
        print("1. 切换账号 (Switch)")
        print("2. 保存当前账号 (Save)")
        print("3. 查看账号列表 (List)")
        print("4. 退出 (Exit)")
        choice = input("请输入选项 (1-4): ").strip()
        
        if choice == '1':
            name = input("请输入要切换到的账号名称: ").strip()
            if name:
                cmd_switch(name)
        elif choice == '2':
            name = input("请输入当前账号要保存的名称: ").strip()
            if name:
                cmd_save(name)
        elif choice == '3':
            cmd_list()
        elif choice == '4' or choice.lower() == 'q':
            print("退出工具。")
            break
        else:
            print("无效的选项，请重新输入。")

def main():
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(description="OpenAI Codex 多账号无缝切换工具")
        subparsers = parser.add_subparsers(dest="command", help="可用命令")
        
        # Save
        parser_save = subparsers.add_parser("save", help="保存当前的账号状态 (例如刚登录完新账号后)")
        parser_save.add_argument("name", help="账号名称（如 work_account, personal_account）")
        
        # Switch
        parser_switch = subparsers.add_parser("switch", help="一键切换到其他账号")
        parser_switch.add_argument("name", help="要切换到的账号名称")
        
        # List
        parser_list = subparsers.add_parser("list", help="列出所有保存的账号")
        
        args = parser.parse_args()
        
        if args.command == "save":
            cmd_save(args.name)
        elif args.command == "switch":
            cmd_switch(args.name)
        elif args.command == "list":
            cmd_list()
        else:
            parser.print_help()
    else:
        # 没有提供参数时，进入交互式菜单
        interactive_menu()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n退出工具。")
        sys.exit(0)
