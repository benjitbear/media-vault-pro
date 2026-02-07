"""
Disc detection and automatic ripping daemon
"""
import os
import time
from pathlib import Path
from typing import Set, Optional, TYPE_CHECKING
import signal
import sys

from .ripper import Ripper
from .metadata import MetadataExtractor
from .utils import load_config, setup_logger, send_notification, configure_notifications

if TYPE_CHECKING:
    from .app_state import AppState


class DiscMonitor:
    """Monitors for disc insertion and triggers automatic ripping"""
    
    def __init__(self, config_path: str = "config.json", app_state: 'AppState' = None):
        """
        Initialize the DiscMonitor
        
        Args:
            config_path: Path to configuration file
            app_state: Optional shared AppState for job queue integration
        """
        self.config = load_config(config_path)
        debug_mode = self.config.get('logging', {}).get('debug', False)
        self.logger = setup_logger('disc_monitor', 'disc_monitor.log', debug=debug_mode)

        # Honour notification config
        notify_enabled = self.config.get('automation', {}).get('notification_enabled', True)
        configure_notifications(notify_enabled)

        self.ripper = Ripper(config_path, app_state=app_state)
        self.metadata_extractor = MetadataExtractor(config_path)
        self.app_state = app_state
        
        self.mount_path = Path(self.config['disc_detection']['mount_path'])
        self.check_interval = self.config['disc_detection']['check_interval_seconds']
        self.known_volumes: Set[str] = set()
        self.running = False
        
        # System volumes to ignore
        self.ignore_volumes = {
            'Macintosh HD',
            'Macintosh HD - Data',
            'Preboot',
            'Recovery',
            'VM',
            'com.apple.TimeMachine.localsnapshots'
        }
        
        self.logger.info("DiscMonitor initialized")
    
    def get_mounted_volumes(self) -> Set[str]:
        """
        Get list of currently mounted volumes
        
        Returns:
            Set of volume names
        """
        volumes = set()
        
        if not self.mount_path.exists():
            return volumes
        
        try:
            for item in self.mount_path.iterdir():
                if item.is_dir() and item.name not in self.ignore_volumes:
                    # Check if it looks like a disc (has VIDEO_TS or similar)
                    if self.is_disc_volume(item):
                        volumes.add(item.name)
        except Exception as e:
            self.logger.error(f"Error scanning volumes: {e}")
        
        return volumes
    
    def is_disc_volume(self, volume_path: Path) -> bool:
        """
        Check if a volume appears to be a DVD/CD
        
        Args:
            volume_path: Path to volume
            
        Returns:
            True if it appears to be a disc
        """
        # Check for VIDEO_TS directory (DVD)
        if (volume_path / 'VIDEO_TS').exists():
            return True
        
        # Check for BDMV directory (Blu-ray)
        if (volume_path / 'BDMV').exists():
            return True
        
        # Check for common disc indicators
        # Could add more sophisticated detection here
        
        return False
    
    def extract_title_from_volume(self, volume_name: str) -> str:
        """
        Extract a clean title from volume name
        
        Args:
            volume_name: Raw volume name
            
        Returns:
            Cleaned title
        """
        # Remove common disc markers
        title = volume_name.replace('_', ' ')
        title = title.replace('DISC', '').replace('DVD', '').strip()
        
        # Remove trailing numbers if they look like disc numbers
        parts = title.split()
        if parts and parts[-1].isdigit() and int(parts[-1]) < 5:
            # Might be "Movie Name 2" - keep it
            pass
        
        return title.strip()
    
    def process_disc(self, volume_name: str):
        """
        Process a newly detected disc.
        If app_state is available, enqueues a job for the worker thread.
        Otherwise, falls back to direct ripping (standalone mode).
        
        Args:
            volume_name: Name of the volume
        """
        volume_path = self.mount_path / volume_name
        
        self.logger.info(f"Processing new disc: {volume_name}")
        send_notification("Disc Detected", f"Found: {volume_name}")
        
        title_guess = self.extract_title_from_volume(volume_name)
        
        # If we have app_state, use the job queue
        if self.app_state:
            job_id = self.app_state.create_job(
                title=title_guess,
                source_path=str(volume_path),
                title_number=1
            )
            self.logger.info(f"Enqueued rip job {job_id} for: {volume_name}")
            self.app_state.broadcast('disc_detected', {
                'volume_name': volume_name,
                'job_id': job_id
            })
            return
        
        # Fallback: direct ripping (standalone mode)
        try:
            self.logger.info(f"Starting direct rip for: {volume_name}")
            output_file = self.ripper.rip_disc(
                source_path=str(volume_path),
                title_name=title_guess
            )
            
            if output_file:
                self.logger.info(f"Rip successful: {output_file}")
                
                if self.config['metadata']['save_to_json']:
                    self.logger.info("Extracting metadata...")
                    metadata = self.metadata_extractor.extract_full_metadata(
                        output_file,
                        title_hint=title_guess
                    )
                    self.metadata_extractor.save_metadata(metadata, title_guess)
                    self.logger.info("Metadata extraction complete")
                
                send_notification("All Done!", f"{title_guess} is ready")
            else:
                self.logger.error(f"Rip failed for: {volume_name}")
                
        except Exception as e:
            self.logger.error(f"Error processing disc {volume_name}: {e}")
            send_notification("Error", f"Failed to process {volume_name}")
    
    def check_for_new_discs(self):
        """Check for newly inserted discs"""
        current_volumes = self.get_mounted_volumes()
        
        # Find new volumes
        new_volumes = current_volumes - self.known_volumes
        
        # Find removed volumes
        removed_volumes = self.known_volumes - current_volumes
        
        # Update known volumes
        self.known_volumes = current_volumes
        
        # Log changes
        if removed_volumes:
            for vol in removed_volumes:
                self.logger.info(f"Disc removed: {vol}")
        
        # Process new discs
        if new_volumes:
            for vol in new_volumes:
                self.logger.info(f"New disc detected: {vol}")
                
                if self.config['automation']['auto_detect_disc']:
                    # Process in a try block to prevent one failure from stopping monitoring
                    try:
                        self.process_disc(vol)
                    except Exception as e:
                        self.logger.error(f"Error processing disc: {e}")
                else:
                    send_notification("Disc Detected", f"{vol} - auto-rip disabled")
    
    def start(self):
        """Start monitoring for discs"""
        self.logger.info("Starting disc monitoring...")
        self.running = True
        
        # Initial scan
        self.known_volumes = self.get_mounted_volumes()
        self.logger.info(f"Initial volumes: {self.known_volumes}")
        
        print(f"🔍 Disc monitor started")
        print(f"📀 Watching: {self.mount_path}")
        print(f"⏱️  Check interval: {self.check_interval} seconds")
        print(f"🤖 Auto-rip: {'Enabled' if self.config['automation']['auto_detect_disc'] else 'Disabled'}")
        print("\nWaiting for discs... (Press Ctrl+C to stop)\n")
        
        send_notification("Disc Monitor Started", "Watching for media")
        
        try:
            while self.running:
                self.check_for_new_discs()
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
            self.stop()
    
    def stop(self):
        """Stop monitoring"""
        self.logger.info("Stopping disc monitoring...")
        self.running = False
        send_notification("Disc Monitor Stopped", "No longer watching for media")
        print("\n👋 Disc monitor stopped")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print("\nReceived shutdown signal...")
    sys.exit(0)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Monitor for disc insertion')
    parser.add_argument('--config', default='config.json', help='Path to config file')
    parser.add_argument('--no-auto-rip', action='store_true', 
                       help='Disable automatic ripping (notify only)')
    
    args = parser.parse_args()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create monitor
    monitor = DiscMonitor(config_path=args.config)
    
    # Override auto-rip if requested
    if args.no_auto_rip:
        monitor.config['automation']['auto_detect_disc'] = False
    
    # Start monitoring
    monitor.start()


if __name__ == '__main__':
    main()
