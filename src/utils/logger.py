#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import os
from datetime import datetime

def setup_logger(log_level=logging.INFO):
    log_dir = "logs"
    if not os.path.exists(log_dir): os.makedirs(log_dir)
    
    formatter = logging.Formatter('%(asctime)s - %(name)-15s - %(levelname)-8s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    if root_logger.hasHandlers(): root_logger.handlers.clear()
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    log_filename = os.path.join(log_dir, f"intervis_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    return logging.getLogger(__name__)