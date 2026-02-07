"""
Main DVD/CD ripping functionality using HandBrake
"""
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime

from .utils import (load_config, setup_logger, sanitize_filename, format_time,
                    send_notification, configure_notifications, print_progress)

if TYPE_CHECKING:
    from .app_state import AppState


class Ripper:
    """Handles DVD/CD ripping operations"""
    
    def __init__(self, config_path: str = "config.json", app_state: 'AppState' = None):
        """
        Initialize the Ripper
        
        Args:
            config_path: Path to configuration file
            app_state: Optional shared AppState for progress reporting
        """
        self.config = load_config(config_path)
        debug_mode = self.config.get('logging', {}).get('debug', False)
        self.logger = setup_logger('ripper', 'ripper.log', debug=debug_mode)
        self.output_dir = Path(self.config['output']['base_directory'])
        self.app_state = app_state
        self.show_progress = self.config.get('logging', {}).get('progress_indicator', True)

        # Honour notification config
        notify_enabled = self.config.get('automation', {}).get('notification_enabled', True)
        configure_notifications(notify_enabled)

        self.logger.info("Ripper initialized")
    
    def check_handbrake_installed(self) -> bool:
        """
        Check if HandBrakeCLI is installed
        
        Returns:
            True if installed, False otherwise
        """
        try:
            result = subprocess.run(
                ['HandBrakeCLI', '--version'],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def detect_disc_info(self, source_path: str) -> Optional[Dict[str, Any]]:
        """
        Detect information about the disc
        
        Args:
            source_path: Path to disc mount point
            
        Returns:
            Dictionary with disc information or None
        """
        self.logger.info(f"Detecting disc info for: {source_path}")
        
        try:
            # Use HandBrake to scan the disc
            result = subprocess.run(
                ['HandBrakeCLI', '--scan', '--input', source_path],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            output = result.stderr  # HandBrake outputs scan to stderr
            
            # Parse output for basic info
            disc_info = {
                'source': source_path,
                'detected': True,
                'scan_output': output
            }
            
            # Try to extract title count
            if 'title(s)' in output.lower():
                # Basic parsing - can be enhanced
                disc_info['has_content'] = True
            
            self.logger.info(f"Disc detected successfully: {source_path}")
            return disc_info
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout while scanning disc: {source_path}")
            return None
        except Exception as e:
            self.logger.error(f"Error detecting disc: {e}")
            return None
    
    def build_handbrake_command(self, source: str, output: str, title: int = 1) -> list:
        """
        Build HandBrakeCLI command
        
        Args:
            source: Source disc path
            output: Output file path
            title: Title number to rip (default: 1 for main feature)
            
        Returns:
            Command as list of arguments
        """
        config = self.config['output']
        hb_config = self.config.get('handbrake', {})
        
        cmd = [
            'HandBrakeCLI',
            '--input', source,
            '--output', output,
            '--title', str(title),
            '--format', config['format'],
            '--encoder', config['video_encoder'],
            '--quality', str(config['quality']),
            '--aencoder', config['audio_encoder'],
            '--ab', config['audio_bitrate'],
        ]
        
        # Add preset if specified
        if 'preset' in hb_config:
            cmd.extend(['--preset', hb_config['preset']])
        
        # Add subtitle extraction
        if self.config['metadata']['extract_subtitles']:
            cmd.extend(['--subtitle', 'scan', '--subtitle-burned=none'])
        
        # Add additional options
        for option in hb_config.get('additional_options', []):
            cmd.append(option)
        
        return cmd
    
    def rip_disc(self, source_path: str, title_name: Optional[str] = None, 
                 title_number: int = 1, job_id: Optional[str] = None) -> Optional[str]:
        """
        Rip a DVD/CD to the output directory
        
        Args:
            source_path: Path to mounted disc
            title_name: Custom name for the output file
            title_number: Title number to rip (1 for main feature)
            job_id: Optional job ID for progress reporting via AppState
            
        Returns:
            Path to output file if successful, None otherwise
        """
        self.logger.info(f"Starting rip process for: {source_path}")
        
        # Check HandBrake is installed
        if not self.check_handbrake_installed():
            self.logger.error("HandBrakeCLI not found. Please install HandBrake.")
            send_notification("Rip Failed", "HandBrakeCLI not installed")
            return None
        
        # Detect disc info
        disc_info = self.detect_disc_info(source_path)
        if not disc_info:
            self.logger.error("Failed to detect disc information")
            send_notification("Rip Failed", "Could not read disc")
            return None
        
        # Generate output filename
        if not title_name:
            # Extract volume name from path
            title_name = Path(source_path).name
        
        sanitized_name = sanitize_filename(title_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{sanitized_name}_{timestamp}.{self.config['output']['format']}"
        output_path = self.output_dir / output_filename
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build command
        cmd = self.build_handbrake_command(source_path, str(output_path), title_number)
        
        self.logger.info(f"Ripping to: {output_path}")
        self.logger.debug(f"Command: {' '.join(cmd)}")
        
        send_notification("Ripping Started", f"Processing: {title_name}")
        
        try:
            # Start ripping process
            start_time = time.time()
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Monitor progress
            for line in process.stdout:
                line = line.strip()
                if line:
                    # Parse and report progress
                    if 'Encoding:' in line or 'ETA' in line:
                        # Parse HandBrake progress: "Encoding: task 1 of 1, 45.23 %"
                        pct_match = re.search(r'(\d+\.\d+)\s*%', line)
                        eta_match = re.search(r'ETA\s+(\S+)', line)
                        fps_match = re.search(r'(\d+\.\d+)\s*fps', line)
                        pct = float(pct_match.group(1)) if pct_match else 0.0
                        eta = eta_match.group(1) if eta_match else None
                        fps = float(fps_match.group(1)) if fps_match else None

                        # Console progress bar
                        if self.show_progress:
                            print_progress(pct, eta=eta, fps=fps, title=title_name or '')

                        # WebSocket progress updates
                        if job_id and self.app_state:
                            if pct_match:
                                self.app_state.update_job_progress(
                                    job_id, pct, eta=eta,
                                    fps=fps, title=title_name
                                )
                    self.logger.debug(line)
            
            process.wait()
            
            elapsed_time = int(time.time() - start_time)
            
            if process.returncode == 0:
                self.logger.info(f"Rip completed successfully in {format_time(elapsed_time)}")
                self.logger.info(f"Output: {output_path}")
                send_notification("Rip Completed", f"{title_name} finished!")
                
                # Auto-eject if configured
                if self.config['automation'].get('auto_eject_after_rip', True):
                    self.eject_disc(source_path)
                
                return str(output_path)
            else:
                self.logger.error(f"Rip failed with return code: {process.returncode}")
                send_notification("Rip Failed", f"{title_name} encountered an error")
                return None
                
        except Exception as e:
            self.logger.error(f"Error during rip process: {e}")
            send_notification("Rip Failed", str(e))
            return None
    
    def eject_disc(self, disc_path: str):
        """
        Eject the disc
        
        Args:
            disc_path: Path to mounted disc
        """
        try:
            subprocess.run(['diskutil', 'eject', disc_path], check=True)
            self.logger.info(f"Ejected disc: {disc_path}")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to eject disc: {e}")
    
    def get_title_list(self, source_path: str) -> list:
        """
        Get list of all titles on the disc
        
        Args:
            source_path: Path to disc
            
        Returns:
            List of title numbers
        """
        # This is a simplified version - can be enhanced with proper parsing
        disc_info = self.detect_disc_info(source_path)
        if disc_info:
            # Parse scan output for title count
            # For now, return [1] as main title
            return [1]
        return []


def main():
    """Main entry point for command-line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Rip DVD/CD media')
    parser.add_argument('--source', required=True, help='Path to disc mount point')
    parser.add_argument('--title', default=None, help='Custom title name')
    parser.add_argument('--title-number', type=int, default=1, help='Title number to rip')
    parser.add_argument('--config', default='config.json', help='Path to config file')
    
    args = parser.parse_args()
    
    ripper = Ripper(config_path=args.config)
    output = ripper.rip_disc(args.source, args.title, args.title_number)
    
    if output:
        print(f"\n✓ Successfully ripped to: {output}")
        return 0
    else:
        print("\n✗ Rip failed. Check logs for details.")
        return 1


if __name__ == '__main__':
    exit(main())
