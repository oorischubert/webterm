from openai import OpenAI
import json, datetime, tempfile
try:
    from .agentToolKit import SiteTree
except ImportError:
    from agentToolKit import SiteTree  # Fallback import if running outside package context

MODEL = "gpt-5-mini"
STT_MODEL = "gpt-4o-mini-transcribe"  # OpenAI's newer transcription model
TTS_MODEL = "tts-1"  # OpenAI's text-to-speech model

class Assistant:
    """Conversation helper that always stays grounded in a SiteTree."""

    def __init__(self, tree: SiteTree | None = None) -> None:
        self.client = OpenAI()
        self.tree: SiteTree | None = tree
        self.messages: list[dict] = []
        self.functions = [LinkTool().desc, ClickTool().desc]  # type: ignore
        self.reset(tree)

    # ---------------- internal helpers ----------------
    def _system_prompt(self, tree: SiteTree) -> str:
        """Craft a single system / user primer that embeds the tree JSON."""
        return (
            f"The current time is {datetime.datetime.now()}. "
            "You are a helpful assistant whose goal is to help users find information "
            "on a specific website. The site structure is provided below in JSON SiteTree "
            "format (all pages + metadata). "
            "When the user asks a question, rely ONLY on that SiteTree to answer. "
            "If the user asks about anything unrelated to the site, respond with: "
            "\"Sorry, I can only discuss content related to <site name>.\" "
            f"\n\nSiteTree JSON:\n{tree.get_json()}"
        )

    def STT(self, audio_bytes: bytes, ) -> str:
        """
        Use OpenAI speech-to-text to transcribe the given audio bytes.
        Uses the gpt-4o-mini-transcribe model for transcription.
        """
        if not audio_bytes:
            return ""
        
        # Detect audio format based on file signature (magic bytes)
        def detect_audio_format(data: bytes) -> str:
            if data.startswith(b'ID3') or data[1:4] == b'ID3':
                return '.mp3'
            elif data.startswith(b'\xff\xfb') or data.startswith(b'\xff\xf3') or data.startswith(b'\xff\xf2'):
                return '.mp3'
            elif data.startswith(b'RIFF') and b'WAVE' in data[:12]:
                return '.wav'
            elif data.startswith(b'ftyp'):
                return '.m4a'
            elif data.startswith(b'OggS'):
                return '.ogg'
            elif data.startswith(b'\x1a\x45\xdf\xa3'):
                return '.webm'
            else:
                # Default to mp3 if we can't detect
                return '.mp3'
        
        # Get the appropriate file extension
        file_suffix = detect_audio_format(audio_bytes)
        
        # Write to a temp file with the correct extension
        with tempfile.NamedTemporaryFile(delete=True, suffix=file_suffix) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            try:
                with open(tmp.name, "rb") as audio_file:
                    transcript = self.client.audio.transcriptions.create(
                        model=STT_MODEL,  # Use your correct STT model name
                        file=audio_file,
                        response_format='text'
                    )
                return transcript
            except Exception as e:
                print(f"STT Error: {e}")
                return ""

    def TTS(self, text: str, voice: str = "alloy", audio_format: str = "mp3") -> bytes:
        """
        Text-to-speech helper. Uses OpenAI TTS to synthesize `text` with the requested `voice`.
        Returns raw audio bytes (e.g., MP3). On error, returns b"".
        """
        if not text:
            return b""
        try:
            # Use the correct OpenAI TTS API
            # Ensure audio_format is a valid literal type
            valid_formats = ["mp3", "opus", "aac", "flac", "wav", "pcm"]
            format_to_use = audio_format if audio_format in valid_formats else "mp3"
            
            resp = self.client.audio.speech.create(
                model=TTS_MODEL,  # Use correct TTS model name
                voice=voice,  # type: ignore
                input=text,
                response_format=format_to_use  # type: ignore
            )
            
            # For the OpenAI client, the response content is accessed directly
            return resp.content
                
        except Exception as e:
            print(f"TTS Error: {e}")
            return b""

    # ---------------- public API ----------------
    def reset(self, tree: SiteTree | None = None) -> None:
        """Clear history and (optionally) switch to a new SiteTree."""
        if tree is not None:
            self.tree = tree
        self.messages = []
        if self.tree:
            self.messages.append(
                {"role": "user", "content": self._system_prompt(self.tree)}
            )

    def audio(self, audio_bytes: bytes, tts: bool = False, voice: str = "alloy", use_tools: bool = True, dense: bool = True, current_url: str | None = None) -> dict:
        """
        Transcribe audio with OpenAI, route the transcript through `self.answer(...)`,
        and return a standardized dict with optional TTS audio.
        dense tells answer to use dense mode, which is more efficient for short answers.
        """
        transcript = self.STT(audio_bytes)

        # If transcription failed, return a clean error message
        if not transcript.strip():
            reply_text = "I couldn't transcribe that audio. Please try again with a clearer recording."
            return {
                "ok": True,
                "transcript": "",
                "reply": reply_text,
                "reply_audio_b64": None
            }

        # Ask the assistant to answer using the transcript text
        try:
            reply_text = self.message(question=transcript, use_tools=use_tools, dense=dense, current_url=current_url)
        except Exception as e:
            reply_text = f"Sorry, I ran into an error while answering: {e}"
        
        for func in [func["name"] for func in self.functions]:
            if isinstance(reply_text, str) and reply_text.strip().startswith(f"{func}:"):
                tts = False  # Disable TTS if a tool call is detected
                    
        # Generate TTS audio if requested
        reply_audio_b64 = None
        if tts and reply_text:
            try:
                import base64
                audio_bytes = self.TTS(reply_text, voice=voice)
                if audio_bytes:
                    reply_audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            except Exception as e:
                print(f"TTS generation failed: {e}")

        return {
            "ok": True,
            "transcript": transcript,
            "reply": reply_text,
            "reply_audio_b64": reply_audio_b64
        }

    def message(self, question: str| None = None, use_tools: bool = True, dense: bool = False, current_url: str | None = None) -> str:
        """
        High-level helper:
        • If a new SiteTree is supplied, reset context first.
        • If no SiteTree, refuse politely.
        • Append the user's question, call the model, return assistant reply.
        """
        if current_url is not None and question is not None:
            question += f" (User currently on page: {current_url})"
        if dense and question is not None:
            question += " (dense mode, if response is NOT a tool call, provide answer in one sentence)"
        # Append user question
        self.messages.append({"role": "user", "content": question})

        resp = self.client.responses.create(
            model=MODEL,
            tools=self.functions if use_tools else None, # type: ignore
            input=self.messages,  # keeps full thread for context # type: ignore
        )
        
        # Walk the output list to handle reasoning → function_call → text patterns from GPT-5
        assistant_text = None
        for item in resp.output:
            itype = getattr(item, "type", None)
            # Skip model-internal reasoning items
            if itype == "reasoning":
                continue
            # Handle function tool calls first
            if itype == "function_call":
                if item.name in ("send_link", "click_element"): # type: ignore
                    try:
                        args = json.loads(item.arguments) # type: ignore
                    except Exception:
                        args = {}
                    url = args.get("url", "")
                    element = args.get("element", "")
                    assistant_text = (
                        f"send_link:{url}" if url else (f"click_element:{element}" if element else "")
                    )
                    break
                # Unknown tool name → ignore and continue searching for text
                continue
            # First assistant text chunk wins
            if hasattr(item, "content") and item.content: # type: ignore
                try:
                    assistant_text = item.content[0].text  # type: ignore[attr-defined]
                except Exception:
                    assistant_text = ""
                break
        if assistant_text is None or assistant_text == "":
            assistant_text = "No response from model."

        self.messages.append({"role": "assistant", "content": assistant_text})
        return assistant_text

class LinkTool:
    def __init__(self):
        self.desc = {
            "type": "function",
            "name": "send_link",
            "description": "Sends user to specified link.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the web page to go to."}
                },
                "required": ["url"],
                "additionalProperties": False
            },
            "strict": True
        }
        
class ClickTool:
      def __init__(self):
        self.desc = {
            "type": "function",
            "name": "click_element",
            "description": "Simulates a click on a specified UI element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element": {"type": "string", "description": "The identifier of the UI element to click."}
                },
                "required": ["element"],
                "additionalProperties": False
            },
            "strict": True
        }

# Test Framework
if __name__ == "__main__":
    import base64
    import random
    import os
    
    def record_audio(duration=10, filename="test_recorded.wav"):
        """
        Record audio for testing purposes using the system's built-in recording tools.
        Returns the path to the recorded file or None if recording failed.
        """
        print(f"🎤 No audio files found. Recording {duration} seconds of audio...")
        print("🔴 Recording will start in 3 seconds. Get ready to speak!")
        
        import time
        import subprocess
        import platform
        
        # Countdown
        for i in range(3, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        
        print("🎙️  RECORDING NOW! Speak clearly...")
        
        try:
            system = platform.system()
            
            if system == "Darwin":  # macOS
                # Use sox if available, fallback to rec
                try:
                    subprocess.run([
                        "rec", "-t", "wav", "-r", "16000", "-c", "1", 
                        filename, "trim", "0", str(duration)
                    ], check=True, capture_output=True)
                except FileNotFoundError:
                    # Fallback to using sox directly
                    subprocess.run([
                        "sox", "-d", "-t", "wav", "-r", "16000", "-c", "1", 
                        filename, "trim", "0", str(duration)
                    ], check=True, capture_output=True)
                    
            elif system == "Linux":
                # Use arecord on Linux
                subprocess.run([
                    "arecord", "-f", "S16_LE", "-r", "16000", "-c", "1", 
                    "-d", str(duration), filename
                ], check=True, capture_output=True)
                
            else:
                print("❌ Audio recording not supported on this system")
                return None
                
            print(f"✅ Recording complete! Saved to {filename}")
            return filename
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Recording failed: {e}")
            print("💡 Install audio tools:")
            print("   macOS: brew install sox")
            print("   Linux: sudo apt-get install alsa-utils")
            return None
        except FileNotFoundError:
            print("❌ Audio recording tools not found")
            print("💡 Install audio tools:")
            print("   macOS: brew install sox")  
            print("   Linux: sudo apt-get install alsa-utils")
            return None

    options = """==== TEST SELECTOR ====
Change this number to select different tests:
1 = Test assistant.answer (text conversation)
2 = Test assistant.STT (speech-to-text only)
3 = Test assistant.TTS (text-to-speech only)
4 = Test assistant.audio (full audio pipeline)"""
    
    print(options)
    try:
        test_number = int(input("Enter test_number (1-4): "))
    except ValueError:
        print("Invalid input. Defaulting to test_number 1.")
        test_number = 5

    if test_number < 1 or test_number > 4:
        print("Invalid test_number. Please enter a number between 1 and 4.")
        test_number = 5

    print(f"=== Running Test #{test_number} ===\n")
    
    # Initialize assistant with test data
    tree = SiteTree().load("./tests/oorischubert.json")
    assistant = Assistant(tree)
    
    if test_number == 1:
        # Test 1: Text conversation (assistant.answer)
        print("🤖 Testing assistant.answer() - Text conversation")
        print("-" * 50)
        
        test_questions = ["What projects does Oori have?"]
        
        for i, question in enumerate(test_questions, 1):
            print(f"\nQ{i}: {question}")
            try:
                answer = assistant.message(question)
                print(f"A{i}: {answer}")
            except Exception as e:
                print(f"❌ Error: {e}")
            print("-" * 30)
    
    elif test_number == 2:
        # Test 2: Speech-to-text (assistant.STT)
        print("🎤 Testing assistant.STT() - Speech-to-text")
        print("-" * 50)
        
        # Check if there are any audio files in the project for testing
        audio_test_files = [
            "./tests/test_audio.wav",
            "./tests/test_audio.mp3",
            "./test.wav",
            "./test.mp3"
        ]
        
        audio_file = None
        for file_path in audio_test_files:
            if os.path.exists(file_path):
                audio_file = file_path
                break
        
        # If no audio file found, record one
        if not audio_file:
            print("⚠️  No audio files found for testing.")
            user_input = input("🎤 Would you like to record 10 seconds of audio now? (y/n): ").lower().strip()
            
            if user_input in ['y', 'yes']:
                recorded_file = record_audio(10, "./tests/test_audio.wav")
                if recorded_file:
                    audio_file = recorded_file
            else:
                print("   Create a test audio file manually:")
                print("   - macOS: say 'Hello WebTerm, what projects does Oori have?' -o test.wav")
                print("   - Linux: espeak 'Hello WebTerm' -w test.wav")
        
        if audio_file:
            print(f"📁 Using audio file: {audio_file}")
            try:
                with open(audio_file, "rb") as f:
                    audio_bytes = f.read()
                
                print("🔄 Transcribing audio...")
                transcript = assistant.STT(audio_bytes)
                print(f"📝 Transcript: '{transcript}'")
                
            except Exception as e:
                print(f"❌ STT Error: {e}")
        else:
            print("⚠️  No audio available for testing STT.")
    
    elif test_number == 3:
        # Test 3: Text-to-speech (assistant.TTS)
        print("🔊 Testing assistant.TTS() - Text-to-speech")
        print("-" * 50)

        test_texts = ["Hey this is WebTerm, im here to help you around this website."]

        voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        
        for i, text in enumerate(test_texts, 1):
            voice = random.choice(voices)  # Randomly select a voice
            print(f"\n🎯 Test {i}: '{text}' (voice: {voice})")
            
            try:
                audio_bytes = assistant.TTS(text, voice=voice)
                
                if audio_bytes:
                    # Save to file for testing
                    output_file = f"./tts_test_{i}_{voice}.mp3"
                    with open(output_file, "wb") as f:
                        f.write(audio_bytes)
                    
                    print(f"✅ Generated {len(audio_bytes)} bytes")
                    print(f"💾 Saved to: {output_file}")
                    
                    # Show base64 preview (first 50 chars)
                    b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                    print(f"📦 Base64 preview: {b64_audio[:50]}...")
                    
                else:
                    print("❌ No audio generated")
                    
            except Exception as e:
                print(f"❌ TTS Error: {e}")
    
    elif test_number == 4:
        # Test 4: Full audio pipeline (assistant.audio)
        print("🎵 Testing assistant.audio() - Full audio pipeline")
        print("-" * 50)
        
        # Check for audio input file
        audio_test_files = [
            "./tests/test_audio.wav",
            "./tests/test_audio.mp3", 
            "./test.wav",
            "./test.mp3",
            "./test_recorded.wav"  # Include previously recorded file
        ]
        
        audio_file = None
        for file_path in audio_test_files:
            if os.path.exists(file_path):
                audio_file = file_path
                break
        
        # If no audio file found, record one
        if not audio_file:
            print("⚠️  No audio files found for testing.")
            user_input = input("🎤 Would you like to record 10 seconds of audio now? (y/n): ").lower().strip()
            
            if user_input in ['y', 'yes']:
                recorded_file = record_audio(10, "./tests/test_audio.wav")
                if recorded_file:
                    audio_file = recorded_file
        
        if audio_file:
            print(f"📁 Using audio file: {audio_file}")
            
            try:
                with open(audio_file, "rb") as f:
                    audio_bytes = f.read()
                
                # Test without TTS
                print("\n🔄 Test 4A: Audio processing (no TTS)")
                result1 = assistant.audio(audio_bytes, tts=False, voice="alloy",use_tools=False,dense=True)
                print(f"✅ Success: {result1['ok']}")
                print(f"📝 Transcript: '{result1['transcript']}'")
                print(f"💬 Reply: '{result1['reply_text']}'")
                print(f"🔊 Audio response: {result1['reply_audio_b64'] is not None}")
                
                # Test with TTS
                print("\n🔄 Test 4B: Audio processing (with TTS)")
                result2 = assistant.audio(audio_bytes, tts=True, voice="nova",use_tools=False,dense=True)
                print(f"✅ Success: {result2['ok']}")
                print(f"📝 Transcript: '{result2['transcript']}'")
                print(f"💬 Reply: '{result2['reply_text']}'")
                
                if result2['reply_audio_b64']:
                    # Save the response audio
                    audio_response = base64.b64decode(result2['reply_audio_b64'])
                    with open("./tests/audio_response_test.mp3", "wb") as f:
                        f.write(audio_response)
                    print(f"🔊 Audio response: {len(audio_response)} bytes")
                    print(f"💾 Saved response to: ./tests/audio_response_test.mp3")
                    print(f"📦 Base64 preview: {result2['reply_audio_b64'][:50]}...")
                else:
                    print("🔊 Audio response: None")
                
            except Exception as e:
                print(f"❌ Audio pipeline error: {e}")
        else:
            print("⚠️  No audio available for testing full audio pipeline.")
            
            # Still demonstrate with dummy audio (will fail transcription but show pipeline)
            print("\n🧪 Testing with dummy audio data...")
            dummy_audio = b"dummy audio data"
            try:
                result = assistant.audio(dummy_audio, tts=True, voice="alloy", use_tools=False)
                print(f"✅ Pipeline completed: {result['ok']}")
                print(f"📝 Transcript: '{result['transcript']}'")
                print(f"💬 Reply: '{result['reply_text']}'")
                print(f"🔊 Audio response: {result['reply_audio_b64'] is not None}")
            except Exception as e:
                print(f"❌ Pipeline error: {e}")
    else:
        print(f"❌ Invalid test_number: {test_number}")
        print("Valid options: 1 (answer), 2 (STT), 3 (TTS), 4 (audio)")
    print(f"\n=== Test #{test_number} Complete ===")