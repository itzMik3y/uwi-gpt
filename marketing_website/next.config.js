/** @type {import('next').NextConfig} */
const nextConfig = {}
const { withContentlayer } = require("next-contentlayer");

module.exports = withContentlayer({
  reactStrictMode: true,
});

module.exports = nextConfig
