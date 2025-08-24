"""网易云音乐二维码登录模块

提供网易云音乐二维码登录功能，包括：
- 二维码生成和显示
- 登录状态检查
- Cookie获取和保存
- 用户友好的交互界面
"""

import sys
import time
import logging
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

try:
    from music_api import QRLoginManager, APIException
    from cookie_manager import CookieManager, CookieException
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保 music_api.py 和 cookie_manager.py 文件存在且可用")
    sys.exit(1)


class QRLoginClient:
    """二维码登录客户端"""
    
    def __init__(self, cookie_file: str = "cookie.txt"):
        """
        初始化二维码登录客户端
        
        Args:
            cookie_file: Cookie保存文件路径
        """
        self.cookie_manager = CookieManager(cookie_file)
        self.qr_manager = QRLoginManager()
        self.logger = logging.getLogger(__name__)
        
        # 配置日志
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def check_existing_login(self) -> bool:
        """检查是否已有有效登录
        
        Returns:
            是否已登录
        """
        try:
            if self.cookie_manager.is_cookie_valid():
                self.logger.info("检测到有效的登录Cookie")
                return True
            else:
                self.logger.info("未检测到有效的登录Cookie")
                return False
        except Exception as e:
            self.logger.error(f"检查登录状态失败: {e}")
            return False
    
    def interactive_login(self) -> Tuple[bool, Optional[str]]:
        """交互式二维码登录
        
        Returns:
            (登录是否成功, 错误信息)
        """
        try:
            print("\n=== 网易云音乐二维码登录 ===")
            
            # 检查现有登录状态
            if self.check_existing_login():
                choice = input("检测到已有有效登录，是否重新登录？(y/N): ").strip().lower()
                if choice not in ['y', 'yes', '是']:
                    print("使用现有登录状态")
                    return True, None
            
            print("\n开始二维码登录流程...")
            
            # 生成二维码
            print("正在生成二维码...")
            qr_result = self.qr_manager.create_qr_login()
            
            if not qr_result['success']:
                error_msg = f"生成二维码失败: {qr_result.get('message', '未知错误')}"
                self.logger.error(error_msg)
                return False, error_msg
            
            qr_key = qr_result['qr_key']
            print(f"\n二维码已生成！")
            print(f"请使用网易云音乐手机APP扫描二维码进行登录")
            print(f"二维码有效期: 3分钟")
            print("\n等待扫码中...")
            
            # 轮询检查登录状态
            max_attempts = 60  # 最多等待5分钟
            attempt = 0
            
            while attempt < max_attempts:
                try:
                    # 检查登录状态
                    status_result = self.qr_manager.check_qr_login(qr_key)
                    
                    if status_result['success']:
                        if status_result['status'] == 'success':
                            # 登录成功
                            cookie = status_result.get('cookie', '')
                            if cookie:
                                # 保存Cookie
                                success = self.save_cookie(cookie)
                                if success:
                                    print("\n✅ 登录成功！Cookie已保存")
                                    return True, None
                                else:
                                    error_msg = "登录成功但Cookie保存失败"
                                    self.logger.error(error_msg)
                                    return False, error_msg
                            else:
                                error_msg = "登录成功但未获取到Cookie"
                                self.logger.error(error_msg)
                                return False, error_msg
                        
                        elif status_result['status'] == 'waiting':
                            # 等待扫码
                            if attempt % 10 == 0:  # 每10次显示一次提示
                                print(f"等待扫码中... ({attempt + 1}/{max_attempts})")
                        
                        elif status_result['status'] == 'scanned':
                            # 已扫码，等待确认
                            print("二维码已扫描，请在手机上确认登录")
                        
                        elif status_result['status'] == 'expired':
                            # 二维码过期
                            error_msg = "二维码已过期，请重新尝试"
                            print(f"\n❌ {error_msg}")
                            return False, error_msg
                        
                        elif status_result['status'] == 'error':
                            # 登录错误
                            error_msg = f"登录失败: {status_result.get('message', '未知错误')}"
                            print(f"\n❌ {error_msg}")
                            return False, error_msg
                    
                    else:
                        self.logger.warning(f"检查登录状态失败: {status_result.get('message', '未知错误')}")
                    
                    # 等待5秒后重试
                    time.sleep(5)
                    attempt += 1
                    
                except KeyboardInterrupt:
                    print("\n用户取消登录")
                    return False, "用户取消登录"
                except Exception as e:
                    self.logger.error(f"检查登录状态时发生错误: {e}")
                    time.sleep(5)
                    attempt += 1
            
            # 超时
            error_msg = "登录超时，请重新尝试"
            print(f"\n❌ {error_msg}")
            return False, error_msg
            
        except APIException as e:
            error_msg = f"API调用失败: {e}"
            self.logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"登录过程中发生未知错误: {e}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def save_cookie(self, cookie: str) -> bool:
        """保存Cookie到文件
        
        Args:
            cookie: Cookie字符串
            
        Returns:
            是否保存成功
        """
        try:
            # 备份现有Cookie（如果存在）
            if self.cookie_manager.cookie_file.exists():
                try:
                    backup_path = self.cookie_manager.backup_cookie()
                    self.logger.info(f"已备份现有Cookie到: {backup_path}")
                except Exception as e:
                    self.logger.warning(f"备份Cookie失败: {e}")
            
            # 保存新Cookie
            success = self.cookie_manager.write_cookie(cookie)
            
            if success:
                # 验证保存的Cookie
                if self.cookie_manager.is_cookie_valid():
                    self.logger.info("Cookie保存并验证成功")
                    return True
                else:
                    self.logger.warning("Cookie保存成功但验证失败")
                    return False
            else:
                self.logger.error("Cookie保存失败")
                return False
                
        except CookieException as e:
            self.logger.error(f"Cookie操作失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"保存Cookie时发生错误: {e}")
            return False
    
    def show_login_info(self) -> None:
        """显示登录信息"""
        try:
            info = self.cookie_manager.get_cookie_info()
            
            print("\n=== 登录状态信息 ===")
            print(f"Cookie文件: {info['file_path']}")
            print(f"文件存在: {'是' if info['file_exists'] else '否'}")
            print(f"Cookie数量: {info['cookie_count']}")
            print(f"登录状态: {'有效' if info['is_valid'] else '无效'}")
            
            if info.get('last_modified'):
                print(f"最后更新: {info['last_modified']}")
            
            if info['is_valid']:
                present_cookies = info.get('important_cookies_present', [])
                print(f"重要Cookie: {', '.join(present_cookies)}")
            else:
                missing_cookies = info.get('missing_important_cookies', [])
                if missing_cookies:
                    print(f"缺少Cookie: {', '.join(missing_cookies)}")
                    
        except Exception as e:
            print(f"获取登录信息失败: {e}")
    
    def logout(self) -> bool:
        """登出（清除Cookie）
        
        Returns:
            是否登出成功
        """
        try:
            # 备份Cookie
            if self.cookie_manager.cookie_file.exists():
                try:
                    backup_path = self.cookie_manager.backup_cookie("logout")
                    print(f"Cookie已备份到: {backup_path}")
                except Exception as e:
                    self.logger.warning(f"备份Cookie失败: {e}")
            
            # 清除Cookie
            success = self.cookie_manager.clear_cookie()
            
            if success:
                print("已成功登出")
                return True
            else:
                print("登出失败")
                return False
                
        except Exception as e:
            print(f"登出时发生错误: {e}")
            return False


def main():
    """主函数"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    client = QRLoginClient()
    
    # 解析命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'login':
            # 执行登录
            success, error = client.interactive_login()
            if success:
                print("\n登录完成！")
                client.show_login_info()
                sys.exit(0)
            else:
                print(f"\n登录失败: {error}")
                sys.exit(1)
        
        elif command == 'status' or command == 'info':
            # 显示登录状态
            client.show_login_info()
            sys.exit(0)
        
        elif command == 'logout':
            # 登出
            success = client.logout()
            sys.exit(0 if success else 1)
        
        elif command == 'help' or command == '-h' or command == '--help':
            # 显示帮助
            print("网易云音乐二维码登录工具")
            print("\n用法:")
            print("  python qr_login.py [命令]")
            print("\n命令:")
            print("  login   - 执行二维码登录")
            print("  status  - 显示登录状态")
            print("  logout  - 登出（清除Cookie）")
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
