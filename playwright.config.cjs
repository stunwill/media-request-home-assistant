const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({testDir:'tests',testMatch:'mobile_visual.spec.cjs',workers:1,timeout:30000,use:{headless:true},reporter:'list'});
