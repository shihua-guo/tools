module.exports = {
  apps: [
    {
      name: "video2text-backend",
      cwd: __dirname,
      script: process.env.PYTHON_BIN || "python",
      args: "backend/main.py",
      interpreter: "none",
      autorestart: true,
      restart_delay: 3000,
      max_restarts: 20,
      env: {
        VIDEO_ROOT: process.env.VIDEO_ROOT || `${__dirname}/videos`,
        OUTPUT_ROOT: process.env.OUTPUT_ROOT || `${__dirname}/backend/output`,
        TASK_DB_PATH: process.env.TASK_DB_PATH || `${__dirname}/backend/tasks.db`,
        QWEN_API_KEY: process.env.QWEN_API_KEY || "",
        PATH: process.env.PATH
      },
      error_file: "/root/.pm2/logs/video2text-backend-error.log",
      out_file: "/root/.pm2/logs/video2text-backend-out.log",
      time: true
    }
  ]
};
