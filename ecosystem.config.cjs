module.exports = {
  apps: [
    {
      name: 'orchestrator',
      script: 'server.py',
      interpreter: 'C:\\Users\\carte\\AppData\\Local\\Programs\\Python\\Python312\\python.exe',
      cwd: 'C:\\Workspace\\Active\\HomeLab',
      autorestart: true,
      watch: false,
      max_restarts: 5,
      restart_delay: 3000,
      windowsHide: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      env: {
        NODE_ENV: 'production',
      },
    },
    {
      name: 'homelab-slack-bot',
      script: 'slack_bot.py',
      interpreter: 'C:\\Users\\carte\\AppData\\Local\\Programs\\Python\\Python312\\python.exe',
      cwd: 'C:\\Workspace\\Active\\HomeLab',
      autorestart: true,
      watch: false,
      max_restarts: 5,
      restart_delay: 3000,
      windowsHide: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
  ],
};
