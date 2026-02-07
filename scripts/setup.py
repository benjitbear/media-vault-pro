"""
Setup script for initial project configuration
"""
import os
import sys
import json
import subprocess
from pathlib import Path


def check_system_dependencies():
    """Check if required system dependencies are installed"""
    print("Checking system dependencies...")
    
    dependencies = {
        'HandBrakeCLI': 'HandBrakeCLI --version',
        'mediainfo': 'mediainfo --version',
    }
    
    missing = []
    for name, command in dependencies.items():
        try:
            subprocess.run(command.split(), capture_output=True, check=True)
            print(f"  ✓ {name} found")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"  ✗ {name} not found")
            missing.append(name)
    
    if missing:
        print("\nMissing dependencies. Install with:")
        print("  brew install handbrake mediainfo")
        return False
    
    return True


def create_directories():
    """Create necessary directories"""
    print("\nCreating directories...")
    
    base_dir = Path(__file__).parent.parent
    
    directories = [
        'logs',
        'data/metadata',
        'data/thumbnails',
    ]
    
    for dir_path in directories:
        full_path = base_dir / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ Created {dir_path}")


def setup_config():
    """Setup configuration files"""
    print("\nSetting up configuration...")
    
    base_dir = Path(__file__).parent.parent
    env_file = base_dir / '.env'
    env_example = base_dir / '.env.example'
    
    if not env_file.exists() and env_example.exists():
        import shutil
        shutil.copy(env_example, env_file)
        print("  ✓ Created .env file from .env.example")
        print("  ⚠ Please edit .env and add your TMDB API key")
    else:
        print("  ✓ .env file already exists")
    
    # Verify config.json
    config_file = base_dir / 'config.json'
    if config_file.exists():
        try:
            with open(config_file) as f:
                json.load(f)
            print("  ✓ config.json is valid")
        except json.JSONDecodeError:
            print("  ✗ config.json is invalid")
            return False
    
    return True


def create_media_output_directory():
    """Create the media library output directory"""
    print("\nSetting up media library directory...")
    
    base_dir = Path(__file__).parent.parent
    config_file = base_dir / 'config.json'
    
    with open(config_file) as f:
        config = json.load(f)
    
    output_dir = Path(config['output']['base_directory'])
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ Created media library at {output_dir}")


def main():
    """Main setup function"""
    print("=" * 60)
    print("Media Ripper Setup")
    print("=" * 60)
    
    # Check dependencies
    if not check_system_dependencies():
        print("\n❌ Setup incomplete. Please install missing dependencies.")
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    # Setup configuration
    if not setup_config():
        print("\n❌ Configuration setup failed.")
        sys.exit(1)
    
    # Create output directory
    try:
        create_media_output_directory()
    except Exception as e:
        print(f"\n❌ Failed to create media library directory: {e}")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ Setup completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Edit .env and add your TMDB API key")
    print("2. Review config.json settings")
    print("3. Run: make dev-install  (to install Python dependencies)")
    print("4. Run: make run-monitor  (to start disc monitoring)")
    print("5. Run: make run-server   (to start web interface)")
    print()


if __name__ == '__main__':
    main()
