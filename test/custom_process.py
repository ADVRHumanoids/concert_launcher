from concert_launcher import executor
import asyncio

proc_name = 'test_custom_process'
machine = 'alaurenzi@localhost'
cmd = 'while true; do echo "Hello from custom process"; sleep 1; done'
session_name = 'test_session'

async def main():
    await executor.execute_custom_process(process=proc_name, machine=machine, cmd=cmd, session=session_name)
    await executor.watch(process=proc_name, cfg=cfg, num_lines=1)
    await asyncio.sleep(5)  # Let the process run for a bit
    await executor.kill(process=proc_name, cfg=cfg)

asyncio.run(main())