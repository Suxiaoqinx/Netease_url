"""网易云音乐二维码登录模块

提供网易云音乐二维码登录功能，包括：
- 二维码生成和显示
- 登录状态检查
- Cookie 获取和保存（直接读写 cookie.txt）
- 用户友好的交互界面
"""

import os
import sys
import time
import shutil
import logging
import datetime
from pathlib import Path
from typing import Optional, Tuple

try:
    from music_api import QRLoginManager, APIException, load_cookies
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保 music_api.py 文件存在且可用")
    sys.exit(1)


# 判断 cookie 是否"有效"：包含任一关键字段即可
IMPORTANT_COOKIE_KEYS = ("MUSIC_U", "__csrf", "NMTID")


class QRLoginClient:
    """二维码登录客户端"""

    def __init__(self, cookie_file: str = "cookie.txt"):
        """
        Args:
            cookie_file: Cookie 保存文件路径
        """
        self.cookie_file = Path(cookie_file)
        self.qr_manager = QRLoginManager()
        self.logger = logging.getLogger(__name__)

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    # ----------- Cookie 文件直接操作 -----------

    def _read_cookie(self) -> str:
        if not self.cookie_file.exists():
            return ""
        try:
            return self.cookie_file.read_text(encoding="utf-8").strip()
        except OSError as e:
            self.logger.error(f"读取 Cookie 失败: {e}")
            return ""

    def _write_cookie(self, cookie: str) -> bool:
        if not cookie or not cookie.strip():
            self.logger.error("Cookie 内容不能为空")
            return False
        try:
            self.cookie_file.write_text(cookie.strip() + "\n", encoding="utf-8")
            return True
        except OSError as e:
            self.logger.error(f"写入 Cookie 失败: {e}")
            return False

    def _backup_cookie(self, suffix: str = "backup") -> Optional[Path]:
        if not self.cookie_file.exists():
            return None
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.cookie_file.with_name(
            f"{self.cookie_file.stem}.{suffix}.{ts}{self.cookie_file.suffix}"
        )
        try:
            shutil.copy2(self.cookie_file, backup_path)
            return backup_path
        except OSError as e:
            self.logger.warning(f"备份 Cookie 失败: {e}")
            return None

    def _clear_cookie(self) -> bool:
        if not self.cookie_file.exists():
            return True
        try:
            self.cookie_file.unlink()
            return True
        except OSError as e:
            self.logger.error(f"清除 Cookie 失败: {e}")
            return False

    def _is_cookie_valid(self) -> bool:
        cookies = load_cookies(str(self.cookie_file))
        return any(k in cookies for k in IMPORTANT_COOKIE_KEYS)

    def _get_cookie_info(self) -> dict:
        cookies = load_cookies(str(self.cookie_file))
        present = [k for k in IMPORTANT_COOKIE_KEYS if k in cookies]
        info = {
            "file_path": str(self.cookie_file.absolute()),
            "file_exists": self.cookie_file.exists(),
            "cookie_count": len(cookies),
            "is_valid": bool(present),
            "important_cookies_present": present,
            "missing_important_cookies": [k for k in IMPORTANT_COOKIE_KEYS if k not in cookies],
        }
        if self.cookie_file.exists():
            try:
                mtime = self.cookie_file.stat().st_mtime
                info["last_modified"] = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                pass
        return info

    # ----------- 业务方法 -----------

    def check_existing_login(self) -> bool:
        """检查是否已有有效登录"""
        try:
            if self._is_cookie_valid():
                self.logger.info("检测到有效的登录 Cookie")
                return True
            self.logger.info("未检测到有效的登录 Cookie")
            return False
        except Exception as e:
            self.logger.error(f"检查登录状态失败: {e}")
            return False

    def interactive_login(self) -> Tuple[bool, Optional[str]]:
        """交互式二维码登录"""
        try:
            print("\n=== 网易云音乐二维码登录 ===")

            if self.check_existing_login():
                choice = input("检测到已有有效登录，是否重新登录？(y/N): ").strip().lower()
                if choice not in ('y', 'yes', '是'):
                    print("使用现有登录状态")
                    return True, None

            print("\n开始二维码登录流程...")
            print("正在生成二维码...")
            qr_result = self.qr_manager.create_qr_login()

            if not qr_result.get('success'):
                error_msg = f"生成二维码失败: {qr_result.get('message', '未知错误')}"
                self.logger.error(error_msg)
                return False, error_msg

            qr_key = qr_result['qr_key']
            print("\n二维码已生成！")
            print("请使用网易云音乐手机 APP 扫描二维码进行登录")
            print("二维码有效期: 3 分钟")
            print("\n等待扫码中...")

            max_attempts = 60  # 最多 5 分钟
            attempt = 0
            while attempt < max_attempts:
                try:
                    status_result = self.qr_manager.check_qr_login(qr_key)

                    if status_result.get('success'):
                        status = status_result.get('status')
                        if status == 'success':
                            cookie = status_result.get('cookie', '')
                            if not cookie:
                                return False, "登录成功但未获取到 Cookie"
                            if self.save_cookie(cookie):
                                print("\n✅ 登录成功！Cookie 已保存")
                                return True, None
                            return False, "登录成功但 Cookie 保存失败"

                        if status == 'waiting' and attempt % 10 == 0:
                            print(f"等待扫码中... ({attempt + 1}/{max_attempts})")
                        elif status == 'scanned':
                            print("二维码已扫描，请在手机上确认登录")
                        elif status == 'expired':
                            print("\n❌ 二维码已过期，请重新尝试")
                            return False, "二维码已过期"
                        elif status == 'error':
                            msg = status_result.get('message', '未知错误')
                            print(f"\n❌ 登录失败: {msg}")
                            return False, f"登录失败: {msg}"
                    else:
                        self.logger.warning(f"检查登录状态失败: {status_result.get('message', '未知错误')}")

                    time.sleep(5)
                    attempt += 1

                except KeyboardInterrupt:
                    print("\n用户取消登录")
                    return False, "用户取消登录"
                except Exception as e:
                    self.logger.error(f"检查登录状态时发生错误: {e}")
                    time.sleep(5)
                    attempt += 1

            print("\n❌ 登录超时，请重新尝试")
            return False, "登录超时"

        except APIException as e:
            self.logger.error(f"API 调用失败: {e}")
            return False, f"API 调用失败: {e}"
        except Exception as e:
            self.logger.error(f"登录过程中发生未知错误: {e}")
            return False, f"登录过程中发生未知错误: {e}"

    def save_cookie(self, cookie: str) -> bool:
        """保存 Cookie 到文件"""
        try:
            if self.cookie_file.exists():
                backup = self._backup_cookie()
                if backup:
                    self.logger.info(f"已备份现有 Cookie 到: {backup}")

            if not self._write_cookie(cookie):
                return False

            if self._is_cookie_valid():
                self.logger.info("Cookie 保存并验证成功")
                return True

            self.logger.warning("Cookie 保存成功但验证失败（缺少关键字段）")
            return False
        except Exception as e:
            self.logger.error(f"保存 Cookie 时发生错误: {e}")
            return False

    def show_login_info(self) -> None:
        """显示登录信息"""
        try:
            info = self._get_cookie_info()
            print("\n=== 登录状态信息 ===")
            print(f"Cookie 文件: {info['file_path']}")
            print(f"文件存在: {'是' if info['file_exists'] else '否'}")
            print(f"Cookie 数量: {info['cookie_count']}")
            print(f"登录状态: {'有效' if info['is_valid'] else '无效'}")
            if info.get("last_modified"):
                print(f"最后更新: {info['last_modified']}")
            if info["is_valid"]:
                present = info.get("important_cookies_present", [])
                print(f"重要 Cookie: {', '.join(present)}")
            else:
                missing = info.get("missing_important_cookies", [])
                if missing:
                    print(f"缺少 Cookie: {', '.join(missing)}")
        except Exception as e:
            print(f"获取登录信息失败: {e}")

    def logout(self) -> bool:
        """登出（清除 Cookie）"""
        try:
            if self.cookie_file.exists():
                backup = self._backup_cookie("logout")
                if backup:
                    print(f"Cookie 已备份到: {backup}")
            if self._clear_cookie():
                print("已成功登出")
                return True
            print("登出失败")
            return False
        except Exception as e:
            print(f"登出时发生错误: {e}")
            return False


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    client = QRLoginClient()

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == 'login':
            success, error = client.interactive_login()
            if success:
                print("\n登录完成！")
                client.show_login_info()
                sys.exit(0)
            print(f"\n登录失败: {error}")
            sys.exit(1)

        elif command in ('status', 'info'):
            client.show_login_info()
            sys.exit(0)

        elif command == 'logout':
            sys.exit(0 if client.logout() else 1)

        elif command in ('help', '-h', '--help'):
            print("网易云音乐二维码登录工具")
            print("\n用法: python qr_login.py [命令]")
            print("\n命令:")
            print("  login   - 执行二维码登录")
            print("  status  - 显示登录状态")
            print("  logout  - 登出（清除 Cookie）")
            print("  help    - 显示此帮助信息")
            print("\n如果不提供命令，将进入交互模式")
            sys.exit(0)

        else:
            print(f"未知命令: {command}")
            print("使用 'python qr_login.py help' 查看帮助")
            sys.exit(1)

    # 交互模式
    try:
        while True:
            print("\n=== 网易云音乐登录工具 ===")
            print("1. 二维码登录")
            print("2. 查看登录状态")
            print("3. 登出")
            print("4. 退出")

            choice = input("\n请选择操作 (1-4): ").strip()

            if choice == '1':
                success, error = client.interactive_login()
                if success:
                    print("\n登录成功！")
                    client.show_login_info()
                else:
                    print(f"\n登录失败: {error}")
            elif choice == '2':
                client.show_login_info()
            elif choice == '3':
                client.logout()
            elif choice == '4':
                print("再见！")
                break
            else:
                print("无效选择，请重试")

    except KeyboardInterrupt:
        print("\n\n程序已退出")
        sys.exit(0)
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
