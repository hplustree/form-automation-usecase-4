export const projects = [
  {
    id: 1,
    name: 'Q1 2024 Invoices',
    documentCount: 12,
    isActive: true,
    type: 'invoice'
  },
  {
    id: 2,
    name: 'Contract Analysis',
    documentCount: 8,
    isActive: false,
    type: 'contract'
  },
  {
    id: 3,
    name: 'Expense Reports',
    documentCount: 15,
    isActive: false,
    type: 'expense'
  }
];

export const processingQueue = [
  {
    id: 1,
    fileName: 'invoice_2024_001.pdf',
    status: 'completed',
    progress: 100
  },
  {
    id: 2,
    fileName: 'contract_alpha.docx',
    status: 'processing',
    progress: 45
  },
  {
    id: 3,
    fileName: 'receipt_march.pdf',
    status: 'pending',
    progress: 0
  }
];

export const extractionResults = [
  {
    id: 1,
    fileName: 'invoice_2024_001.pdf',
    company: 'Acme Corporation',
    date: '2024-01-15',
    amount: '$5,240.00',
    invoice: 'INV-2024-001'
  },
  {
    id: 2,
    fileName: 'contract_alpha.docx',
    company: 'TechStart Inc.',
    date: '2024-02-20',
    amount: '$12,500.00',
    invoice: 'CNT-2024-045'
  }
];

export const keyPointOptions = {
  entityInformation: [
    { id: 'company_name', label: 'Company Name', checked: true },
    { id: 'document_date', label: 'Document Date', checked: true }
  ],
  financialData: [
    { id: 'total_amount', label: 'Total Amount', checked: true },
    { id: 'invoice_number', label: 'Invoice Number', checked: true }
  ],
  contactInformation: [
    { id: 'address', label: 'Address', checked: false },
    { id: 'email', label: 'Email', checked: false },
    { id: 'phone_number', label: 'Phone Number', checked: false }
  ]
};