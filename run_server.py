import os
import uvicorn

if __name__ == '__main__':
    port_str = os.environ.get('PORT', '8000')
    try:
        port = int(port_str)
    except ValueError:
        port = 8000
    access_log = os.environ.get('UVICORN_ACCESS_LOG', 'false').strip().lower() in {'1', 'true', 'yes'}
    print(f'Starting uvicorn on port {port} (access_log={access_log})...')
    uvicorn.run(
        'api:app',
        host='0.0.0.0',
        port=port,
        access_log=access_log,
        timeout_keep_alive=30,
    )
