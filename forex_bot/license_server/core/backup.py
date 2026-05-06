"""
Database backup system - Auto backup + restore
"""

import asyncio
import shutil
import gzip
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import sqlite3

from core.logger import app_logger, db_logger


class DatabaseBackup:
    """Quản lý database backups"""
    
    def __init__(self, db_path: Path, backup_dir: Optional[Path] = None):
        self.db_path = db_path
        self.backup_dir = backup_dir or Path(__file__).resolve().parent.parent / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        
        # Daily backup dir
        self.daily_dir = self.backup_dir / "daily"
        self.daily_dir.mkdir(exist_ok=True)
        
        # Archive dir (older backups)
        self.archive_dir = self.backup_dir / "archive"
        self.archive_dir.mkdir(exist_ok=True)
    
    async def create_backup(self, compress: bool = True) -> Path:
        """
        Tạo backup database
        
        Args:
            compress: Gzip compress không?
        
        Returns:
            Path to backup file
        """
        if not self.db_path.exists():
            db_logger.warning(f"Database not found: {self.db_path}")
            return None
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"forex_license_{timestamp}.db"
        backup_path = self.daily_dir / backup_name
        
        try:
            # Copy database file
            shutil.copy2(self.db_path, backup_path)
            
            # Compress if requested
            if compress:
                compressed_path = backup_path.with_suffix(".db.gz")
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._compress_file,
                    backup_path,
                    compressed_path,
                )
                backup_path.unlink()  # Remove uncompressed
                backup_path = compressed_path
            
            file_size = backup_path.stat().st_size
            db_logger.info(f"✅ Backup created: {backup_path} ({file_size:,.0f} bytes)")
            
            return backup_path
        except Exception as e:
            db_logger.error(f"❌ Backup failed: {str(e)}")
            if backup_path.exists():
                backup_path.unlink()
            return None
    
    async def restore_backup(self, backup_path: Path) -> bool:
        """
        Restore từ backup
        
        Args:
            backup_path: Path to backup file (compressed or not)
        
        Returns:
            True if successful
        """
        if not backup_path.exists():
            db_logger.error(f"Backup file not found: {backup_path}")
            return False
        
        try:
            # Create safety backup of current DB
            safety_backup = self.db_path.with_stem(f"{self.db_path.stem}_safety_backup")
            if self.db_path.exists():
                shutil.copy2(self.db_path, safety_backup)
                db_logger.info(f"Safety backup created: {safety_backup}")
            
            # Decompress if needed
            restore_from = backup_path
            temp_decompressed = None
            
            if backup_path.suffix == ".gz":
                temp_decompressed = backup_path.with_suffix("")
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._decompress_file,
                    backup_path,
                    temp_decompressed,
                )
                restore_from = temp_decompressed
            
            # Restore
            shutil.copy2(restore_from, self.db_path)
            
            # Cleanup temp
            if temp_decompressed and temp_decompressed.exists():
                temp_decompressed.unlink()
            
            db_logger.info(f"✅ Database restored from: {backup_path}")
            return True
            
        except Exception as e:
            db_logger.error(f"❌ Restore failed: {str(e)}")
            return False
    
    async def cleanup_old_backups(self, keep_days: int = 7, max_backups: int = 30):
        """
        Xóa backups cũ
        
        Args:
            keep_days: Giữ lại bao nhiêu ngày
            max_backups: Max số backup file
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=keep_days)
        
        backups = sorted(self.daily_dir.glob("*.db*"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        deleted_count = 0
        
        for backup in backups[max_backups:]:  # Keep top N
            try:
                backup.unlink()
                deleted_count += 1
                db_logger.debug(f"Deleted old backup: {backup.name}")
            except Exception as e:
                db_logger.warning(f"Failed to delete {backup.name}: {e}")
        
        # Also delete by date
        for backup in self.daily_dir.glob("*.db*"):
            if backup.stat().st_mtime < cutoff_date.timestamp():
                try:
                    backup.unlink()
                    deleted_count += 1
                except Exception as e:
                    db_logger.warning(f"Failed to delete {backup.name}: {e}")
        
        if deleted_count > 0:
            db_logger.info(f"Cleaned up {deleted_count} old backup(s)")
    
    def list_backups(self) -> List[dict]:
        """List all available backups"""
        backups = []
        for backup_file in sorted(self.daily_dir.glob("*.db*"), key=lambda x: x.stat().st_mtime, reverse=True):
            stat = backup_file.stat()
            backups.append({
                "name": backup_file.name,
                "path": str(backup_file),
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
        return backups
    
    @staticmethod
    def _compress_file(source: Path, dest: Path):
        """Sync compress helper"""
        with open(source, "rb") as f_in:
            with gzip.open(dest, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
    
    @staticmethod
    def _decompress_file(source: Path, dest: Path):
        """Sync decompress helper"""
        with gzip.open(source, "rb") as f_in:
            with open(dest, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
    
    def verify_backup(self, backup_path: Path) -> bool:
        """Verify backup integrity"""
        if not backup_path.exists():
            return False
        
        try:
            # Decompress if needed
            temp_file = None
            check_path = backup_path
            
            if backup_path.suffix == ".gz":
                temp_file = backup_path.with_suffix("")
                self._decompress_file(backup_path, temp_file)
                check_path = temp_file
            
            # Check if it's valid SQLite DB
            try:
                conn = sqlite3.connect(str(check_path))
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                conn.close()
                
                if temp_file and temp_file.exists():
                    temp_file.unlink()
                
                return len(tables) > 0
            except sqlite3.DatabaseError:
                if temp_file and temp_file.exists():
                    temp_file.unlink()
                return False
        except Exception as e:
            db_logger.error(f"Backup verification failed: {e}")
            return False


async def auto_backup_task(db_backup: DatabaseBackup, interval_hours: int = 24):
    """
    Background task để tự động backup
    
    Args:
        db_backup: DatabaseBackup instance
        interval_hours: Interval giữa các backups
    """
    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)
            await db_backup.create_backup(compress=True)
            await db_backup.cleanup_old_backups(keep_days=7, max_backups=30)
        except Exception as e:
            db_logger.error(f"Auto backup task error: {e}")


# Helper functions
async def init_backup_system(db_path: Path, backup_dir: Optional[Path] = None) -> DatabaseBackup:
    """Initialize backup system and start auto backup task"""
    backup_manager = DatabaseBackup(db_path, backup_dir)
    
    # Create initial backup
    await backup_manager.create_backup(compress=True)
    
    # Start auto backup (24h interval)
    asyncio.create_task(auto_backup_task(backup_manager, interval_hours=24))
    
    app_logger.info("Database backup system initialized")
    return backup_manager
