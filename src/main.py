# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Little Tree Studio <studio@zsxiaoshu.cn>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                -++-                                                
                                               +%%%%#.                                              
                                              *%#%%%%#:                                             
                                             *%#%%%%%%#:                                            
                                           .*%#%%%%%%%%%:                                           
                                          .#%#%%%%%%%%%%%-                                          
                                         .#%#%%%%%%%%%%%%%-                                         
                                        :#%#%%%%%%%%%%%%%%%=                                        
                                       :#%#%%%%%%%%%%%%%%##*=                                       
                                      :##############%%%#****=                                      
                                     -##############%##*******=                                     
                                    -################**********+                                    
                                   =###############*************+                                   
                                  =##############****************+.                                 
                                 =#############*******************+.                                
                                +############*******************+===.                               
                               +###########*******************+==-===.                              
                              *##########*******************+=--===--=.                             
                            .*#########******************+==--==-------.                            
                           .*#######*******************+==-==-----------.                           
                          .*######******************+==-====-------------:                          
                         :*#*#*******************++==-===-----------------:                         
                        :**********************+=======--------------------:                        
                       :********************++========----------------------:                       
                      :*******************+===========-----------------------:                      
                     -*****************++=============------------------------:                     
                    :***************++===============---------------------------                    
                    .+***********++===================-------------------------:                    
                      .::::::::::::::::::::::.:------:........................                      
                                               ::::::.                                              
                                               ------:                                              
                                               ------.                                              
                                               ------.                                              
                                               ------:                                              
                                               ------:                                              
                                              .------:                                              
                                               :....:                                               

🌳 Little Tree Wallpaper Next Flet
Little Tree Studio
https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet

================================================================================

Module Name: [module_name]

Copyright (C) 2024 Little Tree Studio <studio@zsxiaoshu.cn>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

Project Information:
    - Official Website: https://wp.zsxiaoshu.cn/
    - Repository: https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet
    - Issue Tracker: https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet/issues

Module Description:
    Thin entry point delegating to the modular application bootstrap.
"""
from __future__ import annotations

import sys
import traceback

import flet as ft

from app import Application

_START_HIDDEN = any(arg.lower() in {"/hide", "--hide"} for arg in sys.argv[1:])


def main(page: ft.Page) -> None:
    """Delegate to the modular :class:`Application`."""
    Application(start_hidden=_START_HIDDEN)(page)


if __name__ == "__main__":
    try:
        ft.app(target=main)
    except Exception as e:
        # 获取完整的异常信息包括堆栈跟踪
        error_message = f"发生错误: {e!s}\n\n详细信息:\n{traceback.format_exc()}"
        try:
            with open("crush.log", "a", encoding="utf-8") as f:
                f.write(error_message + "\n")
        except Exception:
            pass


