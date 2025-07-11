#!/usr/bin/env python3
"""
Run the complete YouTube Editor workflow
This will:
1. Generate AI edit script (or use cache)
2. Download the YouTube video
3. Create final edit using FFmpeg
"""

import asyncio

from pydantic_scrape.graphs.youtube_editor import create_youtube_edit


async def main():
    """Run the full YouTube Editor workflow"""
    print("🎬 Starting Full YouTube Editor Workflow...")
    print("This will download video and create final edit with FFmpeg")
    print()

    # Run the complete workflow
    result = await create_youtube_edit(
        youtube_url="https://www.youtube.com/watch?v=ZwVPQEGeAVU",
        brief="Cut this down, using jump cuts if neccessary, so the viewer can quickly understand this story.",
        video_projects_dir="./video_projects",
        cache_edit_scripts=True,  # ✅ Use caching
        download_video=True,  # ✅ Download video
        create_final_edit=True,  # ✅ Create final edit with FFmpeg
        enhanced_subtitles=True,  # ✅ Enable enhanced subtitle workflow
    )

    print("\n" + "=" * 60)
    print("📊 WORKFLOW RESULTS")
    print("=" * 60)

    print(f"✅ Success: {result.get('success')}")
    print(f"📁 Project Directory: {result.get('project_dir')}")
    print(f"🎥 Video Path: {result.get('video_path')}")
    print(f"📝 Edit Script: {result.get('edit_script_path')}")
    print(f"🎬 Final Edit: {result.get('final_edit_path')}")
    print(f"🎯 Timeline Created: {result.get('edit_created')}")
    print(f"⏱️ Processing Time: {result.get('processing_time', 0):.2f}s")

    if "ffmpeg_result" in result:
        ffmpeg_result = result["ffmpeg_result"]
        print("\n🎭 FFmpeg Result (Sense Check):")
        print(f"   Success: {ffmpeg_result.get('success')}")
        print(f"   Message: {ffmpeg_result.get('message')}")

        if ffmpeg_result.get("success"):
            print(f"   File Size: {ffmpeg_result.get('file_size_mb', 0):.1f} MB")
            print(f"   Clips Processed: {ffmpeg_result.get('clips_processed', 0)}")

        if "stderr" in ffmpeg_result and ffmpeg_result["stderr"]:
            print(f"   Errors: {ffmpeg_result['stderr']}")

    if "davinci_result" in result:
        davinci_result = result["davinci_result"]
        print("\n🎬 DaVinci Resolve Result:")
        print(f"   Success: {davinci_result.get('success')}")
        print(f"   Message: {davinci_result.get('message')}")
        
        if 'stderr' in davinci_result and davinci_result['stderr']:
            print(f"   Errors: {davinci_result['stderr']}")
        
        if davinci_result.get('success') and davinci_result.get('stdout'):
            # Check for timeline creation confirmation
            stdout = davinci_result.get('stdout', '')
            if "✅ Successfully appended" in stdout and "separate timeline items" in stdout:
                print("   Timeline: ✅ Created with AI-directed cuts as separate clips")
            elif "✅ Successfully appended" in stdout:
                print("   Timeline: ✅ Created with AI-directed cuts")
            else:
                print("   Timeline: ⚠️ Created but may need manual adjustment")

    print("\n" + "=" * 60)

    if result.get("success"):
        print("🎉 YouTube Editor workflow completed successfully!")
        print("📂 Check your project directory for all generated files")
        
        ffmpeg_success = result.get("ffmpeg_result", {}).get("success", False)
        davinci_success = result.get("davinci_result", {}).get("success", False)
        
        if ffmpeg_success and davinci_success:
            print("🎬 Both FFmpeg edit and DaVinci timeline created successfully!")
            print("   • FFmpeg edit ready to watch for sense-checking")
            print("   • DaVinci timeline ready for professional editing")
        elif ffmpeg_success:
            print("🎭 FFmpeg edit created successfully (DaVinci had issues)")
        elif davinci_success:
            print("🎬 DaVinci timeline created successfully (FFmpeg had issues)")
        else:
            print("⚠️  Both editing workflows had issues - check logs above")
    else:
        print("❌ Workflow failed - check error messages above")


if __name__ == "__main__":
    asyncio.run(main())
