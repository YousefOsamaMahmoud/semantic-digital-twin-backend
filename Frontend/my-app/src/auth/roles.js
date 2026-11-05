export const USERS = [
  { id:"admin-01",  username:"admin",       password:"admin123",  name:"System Admin",   email:"admin@sdt-sc.ai",       role:"admin",       roleLabel:"Administrator",      avatar:"SA", avatarColor:"#f59e0b" },
  { id:"log-01",    username:"logistics",   password:"log123",    name:"Ahmed Hassan",   email:"a.hassan@sdt-sc.ai",    role:"logistics",   roleLabel:"Logistics Manager",  avatar:"AH", avatarColor:"#3b82f6" },
  { id:"proc-01",   username:"procurement", password:"proc123",   name:"Sara Khalil",    email:"s.khalil@sdt-sc.ai",    role:"procurement", roleLabel:"Procurement Manager",avatar:"SK", avatarColor:"#8b5cf6" },
  { id:"prod-01",   username:"production",  password:"prod123",   name:"Omar Nasser",    email:"o.nasser@sdt-sc.ai",    role:"production",  roleLabel:"Production Manager", avatar:"ON", avatarColor:"#10b981" },
];

export const ROLE_PAGES = {
  admin:       ["dashboard","sla","inventory","suppliers","violations","ai","alerts"],
  logistics:   ["dashboard","inventory","suppliers","violations","alerts","ai"],
  procurement: ["dashboard","sla","suppliers","violations","alerts","ai"],
  production:  ["dashboard","inventory","violations","alerts","ai"],
};

export const ROLE_HOME = {
  admin:       "dashboard",
  logistics:   "inventory",
  procurement: "sla",
  production:  "dashboard",
};
