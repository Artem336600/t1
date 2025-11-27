"""
Secure Docker Sandbox for Code Execution
Provides isolated environment with resource limits
"""
import docker
import tempfile
import os
import uuid
import time
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from enum import Enum


class SandboxMode(Enum):
    SUBPROCESS = "subprocess"  # Legacy, unsafe
    DOCKER = "docker"          # Secure, isolated
    NSJAIL = "nsjail"          # Advanced isolation


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution"""
    mode: SandboxMode = SandboxMode.DOCKER
    timeout: int = 10  # seconds
    memory_limit: str = "256m"
    cpu_limit: float = 0.5  # 50% of one CPU
    network_disabled: bool = True
    read_only_fs: bool = True
    max_output_size: int = 1024 * 1024  # 1MB


@dataclass
class ExecutionResult:
    """Result of code execution"""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    memory_used: Optional[int] = None
    error: Optional[str] = None


class DockerSandbox:
    """
    Secure Docker-based sandbox for code execution.
    
    Features:
    - Network isolation (--network=none)
    - Memory limits (--memory)
    - CPU limits (--cpus)
    - Read-only filesystem
    - Timeout enforcement
    - No privileged access
    """
    
    SUPPORTED_LANGUAGES = {
        "python": {
            "image": "python:3.11-slim",
            "command": ["python", "/code/script.py"],
            "extension": ".py"
        },
        "javascript": {
            "image": "node:20-slim",
            "command": ["node", "/code/script.js"],
            "extension": ".js"
        },
        "go": {
            "image": "golang:1.21-alpine",
            "command": ["go", "run", "/code/script.go"],
            "extension": ".go"
        }
    }
    
    def __init__(self, config: SandboxConfig = None):
        self.config = config or SandboxConfig()
        self._client = None
        self._images_pulled = set()
    
    @property
    def client(self):
        """Lazy Docker client initialization"""
        if self._client is None:
            try:
                self._client = docker.from_env()
                self._client.ping()
            except Exception as e:
                raise RuntimeError(f"Docker not available: {e}")
        return self._client
    
    def ensure_image(self, language: str) -> str:
        """Pull image if not exists"""
        lang_config = self.SUPPORTED_LANGUAGES.get(language)
        if not lang_config:
            raise ValueError(f"Unsupported language: {language}")
        
        image = lang_config["image"]
        
        if image not in self._images_pulled:
            try:
                self.client.images.get(image)
            except docker.errors.ImageNotFound:
                print(f"Pulling image {image}...")
                self.client.images.pull(image)
            self._images_pulled.add(image)
        
        return image
    
    def execute(
        self,
        code: str,
        language: str = "python",
        stdin: str = "",
        timeout: int = None
    ) -> ExecutionResult:
        """
        Execute code in isolated Docker container.
        
        Args:
            code: Source code to execute
            language: Programming language
            stdin: Input to pass to program
            timeout: Execution timeout (overrides config)
        
        Returns:
            ExecutionResult with stdout, stderr, exit_code
        """
        timeout = timeout or self.config.timeout
        lang_config = self.SUPPORTED_LANGUAGES.get(language)
        
        if not lang_config:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Unsupported language: {language}",
                exit_code=-1,
                execution_time=0,
                error="UNSUPPORTED_LANGUAGE"
            )
        
        # Create temp directory with code
        temp_dir = tempfile.mkdtemp(prefix="sandbox_")
        script_path = os.path.join(temp_dir, f"script{lang_config['extension']}")
        input_path = os.path.join(temp_dir, "input.txt")
        
        try:
            # Write code and input
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            with open(input_path, "w", encoding="utf-8") as f:
                f.write(stdin)
            
            # Ensure image exists
            image = self.ensure_image(language)
            
            # Build command with input redirection
            command = lang_config["command"].copy()
            if stdin:
                # Wrap command to read from input file
                if language == "python":
                    command = ["sh", "-c", f"python /code/script.py < /code/input.txt"]
                elif language == "javascript":
                    command = ["sh", "-c", f"node /code/script.js < /code/input.txt"]
            
            start_time = time.time()
            
            # Run container with security constraints
            container = self.client.containers.run(
                image=image,
                command=command,
                volumes={
                    temp_dir: {"bind": "/code", "mode": "ro"}  # Read-only
                },
                network_mode="none" if self.config.network_disabled else "bridge",
                mem_limit=self.config.memory_limit,
                cpu_period=100000,
                cpu_quota=int(100000 * self.config.cpu_limit),
                read_only=self.config.read_only_fs,
                security_opt=["no-new-privileges"],
                cap_drop=["ALL"],  # Drop all capabilities
                user="nobody",  # Run as unprivileged user
                detach=True,
                stdin_open=False,
                tty=False
            )
            
            try:
                # Wait for completion with timeout
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", -1)
                
                # Get logs
                stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
                stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
                
                # Truncate if too large
                if len(stdout) > self.config.max_output_size:
                    stdout = stdout[:self.config.max_output_size] + "\n... (truncated)"
                if len(stderr) > self.config.max_output_size:
                    stderr = stderr[:self.config.max_output_size] + "\n... (truncated)"
                
                execution_time = time.time() - start_time
                
                return ExecutionResult(
                    success=(exit_code == 0),
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code,
                    execution_time=round(execution_time, 3)
                )
                
            except Exception as e:
                # Timeout or other error
                container.kill()
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"Execution timeout ({timeout}s exceeded)",
                    exit_code=-1,
                    execution_time=timeout,
                    error="TIMEOUT"
                )
            finally:
                # Cleanup container
                try:
                    container.remove(force=True)
                except:
                    pass
                    
        except docker.errors.DockerException as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=0,
                error="DOCKER_ERROR"
            )
        finally:
            # Cleanup temp directory
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
    
    def validate_code(
        self,
        code: str,
        test_cases: list,
        language: str = "python"
    ) -> Dict:
        """
        Validate code against multiple test cases.
        
        Args:
            code: Source code
            test_cases: List of {"input": str, "output": str}
            language: Programming language
        
        Returns:
            Validation results with pass/fail for each test
        """
        results = []
        passed = 0
        failed = 0
        
        for i, test in enumerate(test_cases):
            expected = test.get("output", "").strip()
            stdin = test.get("input", "")
            
            result = self.execute(code, language, stdin)
            actual = result.stdout.strip()
            
            is_passed = (actual == expected) and result.success
            
            results.append({
                "test_number": i + 1,
                "passed": is_passed,
                "expected": expected,
                "actual": actual,
                "execution_time": result.execution_time,
                "error": result.stderr if not result.success else None
            })
            
            if is_passed:
                passed += 1
            else:
                failed += 1
        
        return {
            "all_passed": failed == 0,
            "passed": passed,
            "failed": failed,
            "total": len(test_cases),
            "results": results
        }
    
    def execute_multifile(
        self,
        files: List[Dict],
        entry_point: str = "main.py",
        language: str = "python",
        stdin: str = "",
        timeout: int = None
    ) -> ExecutionResult:
        """
        Execute multi-file project in isolated Docker container.
        
        Args:
            files: List of {"filename": str, "path": str, "content": str}
            entry_point: Main file to run
            language: Programming language
            stdin: Input to pass to program
            timeout: Execution timeout
        
        Returns:
            ExecutionResult with stdout, stderr, exit_code
        """
        timeout = timeout or self.config.timeout
        lang_config = self.SUPPORTED_LANGUAGES.get(language)
        
        if not lang_config:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Unsupported language: {language}",
                exit_code=-1,
                execution_time=0,
                error="UNSUPPORTED_LANGUAGE"
            )
        
        # Create temp directory with all files
        temp_dir = tempfile.mkdtemp(prefix="sandbox_multi_")
        input_path = os.path.join(temp_dir, "input.txt")
        
        try:
            # Write all files
            for file_info in files:
                filename = file_info.get("filename", "")
                file_path = file_info.get("path", "")
                content = file_info.get("content", "")
                
                # Create subdirectories if needed
                if file_path:
                    full_dir = os.path.join(temp_dir, file_path)
                    os.makedirs(full_dir, exist_ok=True)
                    full_path = os.path.join(full_dir, filename)
                else:
                    full_path = os.path.join(temp_dir, filename)
                
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
            
            # Write input
            with open(input_path, "w", encoding="utf-8") as f:
                f.write(stdin)
            
            # Ensure image exists
            image = self.ensure_image(language)
            
            # Build command for entry point
            entry_file = entry_point
            if language == "python":
                if stdin:
                    command = ["sh", "-c", f"cd /code && python {entry_file} < /code/input.txt"]
                else:
                    command = ["sh", "-c", f"cd /code && python {entry_file}"]
            elif language == "javascript":
                if stdin:
                    command = ["sh", "-c", f"cd /code && node {entry_file} < /code/input.txt"]
                else:
                    command = ["sh", "-c", f"cd /code && node {entry_file}"]
            else:
                command = lang_config["command"]
            
            start_time = time.time()
            
            # Run container with security constraints
            container = self.client.containers.run(
                image=image,
                command=command,
                volumes={
                    temp_dir: {"bind": "/code", "mode": "ro"}
                },
                network_mode="none" if self.config.network_disabled else "bridge",
                mem_limit=self.config.memory_limit,
                cpu_period=100000,
                cpu_quota=int(100000 * self.config.cpu_limit),
                read_only=self.config.read_only_fs,
                security_opt=["no-new-privileges"],
                cap_drop=["ALL"],
                user="nobody",
                detach=True,
                stdin_open=False,
                tty=False,
                working_dir="/code"
            )
            
            try:
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", -1)
                
                stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
                stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
                
                if len(stdout) > self.config.max_output_size:
                    stdout = stdout[:self.config.max_output_size] + "\n... (truncated)"
                if len(stderr) > self.config.max_output_size:
                    stderr = stderr[:self.config.max_output_size] + "\n... (truncated)"
                
                execution_time = time.time() - start_time
                
                return ExecutionResult(
                    success=(exit_code == 0),
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code,
                    execution_time=round(execution_time, 3)
                )
                
            except Exception as e:
                container.kill()
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"Execution timeout ({timeout}s exceeded)",
                    exit_code=-1,
                    execution_time=timeout,
                    error="TIMEOUT"
                )
            finally:
                try:
                    container.remove(force=True)
                except:
                    pass
                    
        except docker.errors.DockerException as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=0,
                error="DOCKER_ERROR"
            )
        finally:
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
    
    def validate_multifile(
        self,
        files: List[Dict],
        entry_point: str,
        test_cases: List[Dict],
        language: str = "python",
        unit_tests: List[Dict] = None,
        test_file: str = None
    ) -> Dict:
        """
        Validate multi-file project against test cases.
        
        Args:
            files: List of project files
            entry_point: Main file to run
            test_cases: stdin/stdout test cases
            language: Programming language
            unit_tests: Optional unit tests to run
            test_file: Optional custom test file content
        
        Returns:
            Validation results
        """
        results = []
        passed = 0
        failed = 0
        total_points = 0
        earned_points = 0
        
        # Run stdin/stdout tests
        for i, test in enumerate(test_cases):
            expected = test.get("output", "").strip()
            stdin = test.get("input", "")
            points = test.get("points", 10)
            total_points += points
            
            result = self.execute_multifile(files, entry_point, language, stdin)
            actual = result.stdout.strip()
            
            is_passed = (actual == expected) and result.success
            
            results.append({
                "test_number": i + 1,
                "type": "io",
                "passed": is_passed,
                "expected": expected,
                "actual": actual,
                "execution_time": result.execution_time,
                "error": result.stderr if not result.success else None,
                "points": points if is_passed else 0,
                "max_points": points
            })
            
            if is_passed:
                passed += 1
                earned_points += points
            else:
                failed += 1
        
        # Run unit tests if provided
        if unit_tests:
            for i, unit_test in enumerate(unit_tests):
                test_name = unit_test.get("test_name", f"test_{i}")
                test_code = unit_test.get("test_code", "")
                points = unit_test.get("points", 10)
                total_points += points
                
                # Create test file and add to files
                test_files = files.copy()
                test_files.append({
                    "filename": "_test_runner.py",
                    "path": "",
                    "content": test_code
                })
                
                result = self.execute_multifile(
                    test_files, 
                    "_test_runner.py", 
                    language
                )
                
                is_passed = result.success and result.exit_code == 0
                
                results.append({
                    "test_number": len(test_cases) + i + 1,
                    "type": "unit",
                    "name": test_name,
                    "passed": is_passed,
                    "output": result.stdout[:500],
                    "error": result.stderr[:500] if result.stderr else None,
                    "execution_time": result.execution_time,
                    "points": points if is_passed else 0,
                    "max_points": points
                })
                
                if is_passed:
                    passed += 1
                    earned_points += points
                else:
                    failed += 1
        
        # Run custom test file if provided
        if test_file:
            test_files = files.copy()
            test_files.append({
                "filename": "_custom_test.py",
                "path": "",
                "content": test_file
            })
            
            result = self.execute_multifile(test_files, "_custom_test.py", language)
            
            is_passed = result.success and result.exit_code == 0
            points = 20  # Custom test worth 20 points
            total_points += points
            
            results.append({
                "test_number": len(results) + 1,
                "type": "custom",
                "passed": is_passed,
                "output": result.stdout[:500],
                "error": result.stderr[:500] if result.stderr else None,
                "execution_time": result.execution_time,
                "points": points if is_passed else 0,
                "max_points": points
            })
            
            if is_passed:
                passed += 1
                earned_points += points
            else:
                failed += 1
        
        score = (earned_points / total_points * 100) if total_points > 0 else 0
        
        return {
            "all_passed": failed == 0,
            "passed": passed,
            "failed": failed,
            "total": len(results),
            "score": round(score, 1),
            "earned_points": earned_points,
            "total_points": total_points,
            "results": results
        }


class SubprocessSandbox:
    """
    Legacy subprocess-based execution (UNSAFE - for development only).
    Use DockerSandbox in production!
    """
    
    def execute(
        self,
        code: str,
        language: str = "python",
        stdin: str = "",
        timeout: int = 5
    ) -> ExecutionResult:
        import subprocess
        import tempfile
        
        if language != "python":
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="Only Python supported in subprocess mode",
                exit_code=-1,
                execution_time=0
            )
        
        # Write code to temp file (needed for input() to work)
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8')
        try:
            temp_file.write(code)
            temp_file.close()
            
            start_time = time.time()
            
            result = subprocess.run(
                ["python", temp_file.name],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return ExecutionResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time=round(time.time() - start_time, 3)
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Timeout ({timeout}s)",
                exit_code=-1,
                execution_time=timeout,
                error="TIMEOUT"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=0,
                error="EXECUTION_ERROR"
            )
        finally:
            try:
                os.unlink(temp_file.name)
            except:
                pass
    
    def validate_code(
        self,
        code: str,
        test_cases: list,
        language: str = "python"
    ) -> Dict:
        """Validate code against test cases using subprocess"""
        results = []
        passed = 0
        failed = 0
        
        for i, test in enumerate(test_cases):
            expected = test.get("output", "").strip()
            stdin = test.get("input", "")
            
            result = self.execute(code, language, stdin)
            actual = result.stdout.strip()
            
            is_passed = (actual == expected) and result.success
            
            results.append({
                "test_number": i + 1,
                "passed": is_passed,
                "expected": expected,
                "actual": actual,
                "execution_time": result.execution_time,
                "error": result.stderr if not result.success else None
            })
            
            if is_passed:
                passed += 1
            else:
                failed += 1
        
        return {
            "all_passed": failed == 0,
            "passed": passed,
            "failed": failed,
            "total": len(test_cases),
            "results": results
        }
    
    def execute_multifile(
        self,
        files: List[Dict],
        entry_point: str = "main.py",
        language: str = "python",
        stdin: str = "",
        timeout: int = 10
    ) -> ExecutionResult:
        """Execute multi-file project using subprocess (limited support)"""
        import subprocess
        import tempfile
        import shutil
        
        if language != "python":
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="Only Python supported in subprocess mode",
                exit_code=-1,
                execution_time=0
            )
        
        # Create temp directory with all files
        temp_dir = tempfile.mkdtemp(prefix="subprocess_multi_")
        
        try:
            # Write all files
            for file_info in files:
                filename = file_info.get("filename", "")
                file_path = file_info.get("path", "")
                content = file_info.get("content", "")
                
                if file_path:
                    full_dir = os.path.join(temp_dir, file_path)
                    os.makedirs(full_dir, exist_ok=True)
                    full_path = os.path.join(full_dir, filename)
                else:
                    full_path = os.path.join(temp_dir, filename)
                
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
            
            start_time = time.time()
            
            result = subprocess.run(
                ["python", entry_point],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=temp_dir
            )
            
            return ExecutionResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time=round(time.time() - start_time, 3)
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Timeout ({timeout}s)",
                exit_code=-1,
                execution_time=timeout,
                error="TIMEOUT"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=0,
                error="EXECUTION_ERROR"
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def validate_multifile(
        self,
        files: List[Dict],
        entry_point: str,
        test_cases: List[Dict],
        language: str = "python",
        unit_tests: List[Dict] = None,
        test_file: str = None
    ) -> Dict:
        """Validate multi-file project using subprocess"""
        results = []
        passed = 0
        failed = 0
        
        for i, test in enumerate(test_cases):
            expected = test.get("output", "").strip()
            stdin = test.get("input", "")
            
            result = self.execute_multifile(files, entry_point, language, stdin)
            actual = result.stdout.strip()
            
            is_passed = (actual == expected) and result.success
            
            results.append({
                "test_number": i + 1,
                "type": "io",
                "passed": is_passed,
                "expected": expected,
                "actual": actual,
                "execution_time": result.execution_time,
                "error": result.stderr if not result.success else None
            })
            
            if is_passed:
                passed += 1
            else:
                failed += 1
        
        return {
            "all_passed": failed == 0,
            "passed": passed,
            "failed": failed,
            "total": len(results),
            "results": results
        }


def get_sandbox(mode: str = None) -> DockerSandbox:
    """
    Factory function to get appropriate sandbox.
    
    Args:
        mode: "docker" (default), "subprocess" (unsafe)
    
    Returns:
        Sandbox instance
    """
    mode = mode or os.getenv("SANDBOX_MODE", "docker")
    
    if mode == "subprocess":
        print("⚠️  WARNING: Using unsafe subprocess mode!")
        return SubprocessSandbox()
    
    return DockerSandbox()
