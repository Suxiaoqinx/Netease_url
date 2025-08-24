"""Cookie管理器模块

提供网易云音乐Cookie管理功能，包括：
- Cookie文件读取和写入
- Cookie格式验证和解析
- Cookie有效性检查
- 自动过期处理
"""

import os
import json
import time
from typing import Dict, Optional, List, Tuple, Any
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging


@dataclass
class CookieInfo:
    """Cookie信息数据类"""
    name: str
    value: str
    domain: str = ""
    path: str = "/"
    expires: Optional[int] = None
    secure: bool = False
    http_only: bool = False


class CookieException(Exception):
    """Cookie相关异常类"""
    pass


class CookieManager:
    """Cookie管理器主类"""
    
    def __init__(self, cookie_file: str = "cookie.txt"):
        """
        初始化Cookie管理器
        
        Args:
            cookie_file: Cookie文件路径
        """
        self.cookie_file = Path(cookie_file)
        self.logger = logging.getLogger(__name__)
        
        # 网易云音乐相关的重要Cookie字段
        self.important_cookies = {
            'MUSIC_U',      # 用户标识
            'MUSIC_A',      # 用户认证
            '__csrf',       # CSRF令牌
            'NMTID',        # 设备标识
            'WEVNSM',       # 会话管理
            'WNMCID',       # 客户端标识
        }
        
        # 确保cookie文件存在
        self._ensure_cookie_file_exists()
    
    def _ensure_cookie_file_exists(self) -> None:
        """确保Cookie文件存在"""
        if not self.cookie_file.exists():
            self.cookie_file.touch()
            self.logger.info(f"创建Cookie文件: {self.cookie_file}")
    
    def read_cookie(self) -> str:
        """读取Cookie文件内容
        
        Returns:
            Cookie字符串内容
            
        Raises:
            CookieException: 读取失败时抛出
        """
        try:
            if not self.cookie_file.exists():
                self.logger.warning(f"Cookie文件不存在: {self.cookie_file}")
                return ""
            
            content = self.cookie_file.read_text(encoding='utf-8').strip()
            
            if not content:
                self.logger.warning("Cookie文件为空")
                return ""
            
            self.logger.debug(f"成功读取Cookie文件，长度: {len(content)}")
            return content
            
        except UnicodeDecodeError as e:
            raise CookieException(f"Cookie文件编码错误: {e}")
        except PermissionError as e:
            raise CookieException(f"没有权限读取Cookie文件: {e}")
        except Exception as e:
            raise CookieException(f"读取Cookie文件失败: {e}")
    
    def write_cookie(self, cookie_content: str) -> bool:
        """写入Cookie到文件
        
        Args:
            cookie_content: Cookie内容字符串
            
        Returns:
            是否写入成功
            
        Raises:
            CookieException: 写入失败时抛出
        """
        try:
            if not cookie_content or not cookie_content.strip():
                raise CookieException("Cookie内容不能为空")
            
            # 验证Cookie格式
            if not self.validate_cookie_format(cookie_content):
                raise CookieException("Cookie格式无效")
            
            # 写入文件
            self.cookie_file.write_text(cookie_content.strip(), encoding='utf-8')
            
            self.logger.info(f"成功写入Cookie到文件: {self.cookie_file}")
            return True
            
        except PermissionError as e:
            raise CookieException(f"没有权限写入Cookie文件: {e}")
        except Exception as e:
            raise CookieException(f"写入Cookie文件失败: {e}")
    
    def parse_cookies(self) -> Dict[str, str]:
        """解析Cookie字符串为字典
        
        Returns:
            Cookie字典
            
        Raises:
            CookieException: 解析失败时抛出
        """
        try:
            cookie_content = self.read_cookie()
            if not cookie_content:
                return {}
            
            return self.parse_cookie_string(cookie_content)
            
        except Exception as e:
            raise CookieException(f"解析Cookie失败: {e}")
    
    def parse_cookie_string(self, cookie_string: str) -> Dict[str, str]:
        """解析Cookie字符串
        
        Args:
            cookie_string: Cookie字符串
            
        Returns:
            Cookie字典
        """
        if not cookie_string or not cookie_string.strip():
            return {}
        
        cookies = {}
        
        try:
            # 处理多种Cookie格式
            cookie_string = cookie_string.strip()
            
            # 分割Cookie项
            cookie_pairs = []
            if ';' in cookie_string:
                cookie_pairs = cookie_string.split(';')
            elif '\n' in cookie_string:
                cookie_pairs = cookie_string.split('\n')
            else:
                cookie_pairs = [cookie_string]
            
            for pair in cookie_pairs:
                pair = pair.strip()
                if not pair or '=' not in pair:
                    continue
                
                # 分割键值对
                key, value = pair.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                if key and value:
                    cookies[key] = value
            
            self.logger.debug(f"解析得到 {len(cookies)} 个Cookie项")
            return cookies
            
        except Exception as e:
            self.logger.error(f"解析Cookie字符串失败: {e}")
            return {}
    
    def validate_cookie_format(self, cookie_string: str) -> bool:
        """验证Cookie格式是否有效
        
        Args:
            cookie_string: Cookie字符串
            
        Returns:
            是否格式有效
        """
        if not cookie_string or not cookie_string.strip():
            return False
        
        try:
            # 尝试解析Cookie
            cookies = self.parse_cookie_string(cookie_string)
            
            # 检查是否至少包含一个有效的Cookie
            if not cookies:
                return False
            
            # 检查Cookie名称是否合法
            for name, value in cookies.items():
                if not name or not isinstance(name, str):
                    return False
                if not isinstance(value, str):
                    return False
                # 检查是否包含非法字符
                if any(char in name for char in [' ', '\t', '\n', '\r', ';', ',']):
                    return False
            
            return True
            
        except Exception:
            return False
    
    def is_cookie_valid(self) -> bool:
        """检查Cookie是否有效
        
        Returns:
            Cookie是否有效
        """
        try:
            cookies = self.parse_cookies()
            
            if not cookies:
                self.logger.warning("Cookie为空")
                return False
            
            # 检查重要Cookie是否存在
            missing_cookies = self.important_cookies - set(cookies.keys())
            if missing_cookies:
                self.logger.warning(f"缺少重要Cookie: {missing_cookies}")
                return False
            
            # 检查MUSIC_U是否有效（基本验证）
            music_u = cookies.get('MUSIC_U', '')
            if not music_u or len(music_u) < 10:
                self.logger.warning("MUSIC_U Cookie无效")
                return False
            
            self.logger.debug("Cookie验证通过")
            return True
            
        except Exception as e:
            self.logger.error(f"Cookie验证失败: {e}")
            return False
    
    def get_cookie_info(self) -> Dict[str, Any]:
        """获取Cookie详细信息
        
        Returns:
            包含Cookie信息的字典
        """
        try:
            cookies = self.parse_cookies()
            
            info = {
                'file_path': str(self.cookie_file),
                'file_exists': self.cookie_file.exists(),
                'file_size': self.cookie_file.stat().st_size if self.cookie_file.exists() else 0,
                'cookie_count': len(cookies),
                'is_valid': self.is_cookie_valid(),
                'important_cookies_present': list(self.important_cookies & set(cookies.keys())),
                'missing_important_cookies': list(self.important_cookies - set(cookies.keys())),
                'all_cookie_names': list(cookies.keys())
            }
            
            # 添加文件修改时间
            if self.cookie_file.exists():
                mtime = self.cookie_file.stat().st_mtime
                info['last_modified'] = datetime.fromtimestamp(mtime).isoformat()
            
            return info
            
        except Exception as e:
            return {
                'error': str(e),
                'file_path': str(self.cookie_file),
                'file_exists': False,
                'is_valid': False
            }
    
    def backup_cookie(self, backup_suffix: str = None) -> str:
        """备份Cookie文件
        
        Args:
            backup_suffix: 备份文件后缀，默认使用时间戳
            
        Returns:
            备份文件路径
            
        Raises:
            CookieException: 备份失败时抛出
        """
        try:
            if not self.cookie_file.exists():
                raise CookieException("Cookie文件不存在，无法备份")
            
            if backup_suffix is None:
                backup_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            backup_path = self.cookie_file.with_suffix(f".{backup_suffix}.bak")
            
            # 复制文件内容
            content = self.cookie_file.read_text(encoding='utf-8')
            backup_path.write_text(content, encoding='utf-8')
            
            self.logger.info(f"Cookie备份成功: {backup_path}")
            return str(backup_path)
            
        except Exception as e:
            raise CookieException(f"备份Cookie文件失败: {e}")
    
    def restore_cookie(self, backup_path: str) -> bool:
        """从备份恢复Cookie
        
        Args:
            backup_path: 备份文件路径
            
        Returns:
            是否恢复成功
            
        Raises:
            CookieException: 恢复失败时抛出
        """
        try:
            backup_file = Path(backup_path)
            if not backup_file.exists():
                raise CookieException(f"备份文件不存在: {backup_path}")
            
            # 读取备份内容
            backup_content = backup_file.read_text(encoding='utf-8')
            
            # 验证备份内容
            if not self.validate_cookie_format(backup_content):
                raise CookieException("备份文件中的Cookie格式无效")
            
            # 写入当前Cookie文件
            self.write_cookie(backup_content)
            
            self.logger.info(f"从备份恢复Cookie成功: {backup_path}")
            return True
            
        except Exception as e:
            raise CookieException(f"恢复Cookie失败: {e}")
    
    def clear_cookie(self) -> bool:
        """清空Cookie文件
        
        Returns:
            是否清空成功
        """
        try:
            if self.cookie_file.exists():
                self.cookie_file.write_text("", encoding='utf-8')
                self.logger.info("Cookie文件已清空")
            return True
            
        except Exception as e:
            self.logger.error(f"清空Cookie文件失败: {e}")
            return False
    
    def update_cookie(self, new_cookies: Dict[str, str]) -> bool:
        """更新Cookie
        
        Args:
            new_cookies: 新的Cookie字典
            
        Returns:
            是否更新成功
        """
        try:
            if not new_cookies:
                raise CookieException("新Cookie不能为空")
            
            # 读取现有Cookie
            existing_cookies = self.parse_cookies()
            
            # 合并Cookie
            existing_cookies.update(new_cookies)
            
            # 转换为Cookie字符串
            cookie_string = '; '.join(f"{k}={v}" for k, v in existing_cookies.items())
            
            # 写入文件
            return self.write_cookie(cookie_string)
            
        except Exception as e:
            self.logger.error(f"更新Cookie失败: {e}")
            return False
    
    def get_cookie_for_request(self) -> Dict[str, str]:
        """获取用于HTTP请求的Cookie字典
        
        Returns:
            适用于requests库的Cookie字典
        """
        try:
            cookies = self.parse_cookies()
            
            # 过滤掉空值
            filtered_cookies = {k: v for k, v in cookies.items() if k and v}
            
            return filtered_cookies
            
        except Exception as e:
            self.logger.error(f"获取请求Cookie失败: {e}")
            return {}
    
    def format_cookie_string(self, cookies: Dict[str, str]) -> str:
        """将Cookie字典格式化为字符串
        
        Args:
            cookies: Cookie字典
            
        Returns:
            Cookie字符串
        """
        if not cookies:
            return ""
        
        return '; '.join(f"{k}={v}" for k, v in cookies.items() if k and v)
    
    def __str__(self) -> str:
        """字符串表示"""
        info = self.get_cookie_info()
        return f"CookieManager(file={info['file_path']}, valid={info['is_valid']}, count={info['cookie_count']})"
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()


if __name__ == "__main__":
    # 测试代码
    import sys
    
    # 配置日志
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    manager = CookieManager()
    
    print("Cookie管理器模块")
    print("支持的功能:")
    print("- Cookie文件读写")
    print("- Cookie格式验证")
    print("- Cookie有效性检查")
    print("- Cookie备份和恢复")
    print("- Cookie信息查看")
    
    # 显示当前Cookie信息
    info = manager.get_cookie_info()
    print(f"\n当前Cookie状态: {manager}")
    print(f"详细信息: {info}")
