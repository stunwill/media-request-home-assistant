const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({
 testDir:'tests',testMatch:['mobile_visual.spec.cjs','management.spec.cjs','download_interaction.spec.cjs'],
 workers:1,timeout:30000,use:{headless:true,locale:'en-AU',timezoneId:'Australia/Melbourne'},reporter:'list',
 projects:[{name:'chromium',use:{browserName:'chromium'}},
  {name:'webkit',testMatch:['download_interaction.spec.cjs'],use:{browserName:'webkit'}}]
});
