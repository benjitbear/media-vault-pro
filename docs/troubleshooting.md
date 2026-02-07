# Troubleshooting Guide

## Common Issues

### Disc Not Detected

**Symptoms:** Disc monitor doesn't detect inserted discs.

**Solutions:**
1. Check that the disc is properly mounted
   ```bash
   ls /Volumes/
   ```
2. Verify disc detection interval in config.json
3. Ensure you have read permissions on /Volumes/
4. Check logs/disc_monitor.log for errors

### HandBrake Errors

**Symptoms:** "HandBrakeCLI not found" or encoding errors.

**Solutions:**
1. Install HandBrakeCLI:
   ```bash
   brew install handbrake
   ```
2. Verify installation:
   ```bash
   which HandBrakeCLI
   ```
3. Check HandBrake version compatibility:
   ```bash
   HandBrakeCLI --version
   ```

### Copy Protection Issues

**Symptoms:** "Failed to open DVD" or "No valid source found"

**Solutions:**
1. Install MakeMKV:
   ```bash
   brew install makemkv
   ```
2. Use MakeMKV to decrypt first, then rip with HandBrake
3. Check that libdvdcss is installed

### Metadata Lookup Failures

**Symptoms:** Missing movie information, no cover art.

**Solutions:**
1. Verify TMDB API key in .env file
2. Check internet connection
3. Verify disc has valid title metadata
4. Manually edit metadata JSON files in data/metadata/

### Web Server Won't Start

**Symptoms:** "Address already in use" or port binding errors.

**Solutions:**
1. Check if another service is using port 8096:
   ```bash
   lsof -i :8096
   ```
2. Change port in config.json
3. Ensure firewall allows incoming connections

### Low Quality Output

**Symptoms:** Video quality is poor or file size too large.

**Solutions:**
1. Adjust quality setting in config.json (lower = better quality, 18-22 recommended)
2. Check HandBrake preset settings
3. Verify source disc quality
4. Consider using different encoder (H.265 for better compression)

### Insufficient Disk Space

**Symptoms:** Ripping fails partway through or errors about disk space.

**Solutions:**
1. Check available space:
   ```bash
   df -h
   ```
2. Clean up old/unwanted rips
3. Move media library to external drive
4. Adjust output quality settings to reduce file size

### Permission Errors

**Symptoms:** "Permission denied" when writing files.

**Solutions:**
1. Check directory permissions:
   ```bash
   ls -la /Users/poppemacmini/Documents/MediaLibrary
   ```
2. Fix permissions:
   ```bash
   chmod -R 755 /Users/poppemacmini/Documents/MediaLibrary
   ```
3. Run scripts with appropriate user privileges

## Logs

Always check the relevant log files:
- `logs/ripper.log` - Ripping operations
- `logs/metadata.log` - Metadata extraction
- `logs/disc_monitor.log` - Disc detection
- `logs/web_server.log` - Web interface

## Getting Help

If you can't resolve the issue:
1. Check the logs for detailed error messages
2. Search existing GitHub issues
3. Create a new issue with:
   - Error message
   - Relevant log excerpts
   - System information (OS, Python version)
   - Steps to reproduce
