const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 800 });
  
  await page.goto('https://docs.google.com/spreadsheets/d/1pzyG3r9CtMIoHqf62qB6E0pG8Rq3MVr4WZutGe1idxo/edit?usp=drivesdk', { waitUntil: 'networkidle2' });
  
  // Take screenshot to see if we can edit
  await page.screenshot({ path: '/home/students/.gemini/antigravity-cli/brain/623e35f6-13d3-4fd9-b81e-e2dd718c67f2/sheet_screenshot.png' });
  
  // Check if "View only" is present
  const viewOnly = await page.evaluate(() => {
    return document.body.innerText.includes('View only');
  });
  console.log("Is View Only? " + viewOnly);
  
  await browser.close();
})();
